from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from agent_orchestrator.api.deps import (
    get_job_event_stream,
    get_live_event_bus,
    get_mcp_tool_catalog,
    get_repository,
    get_skill_registry,
    require_job,
)
from agent_orchestrator.api.serializers import (
    serialize_event,
    serialize_job,
    serialize_job_detail,
    serialize_job_question,
)
from agent_orchestrator.api.tool_catalog import list_effective_session_tools
from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
from agent_orchestrator.repositories.questions import QUESTION_STATUS_PENDING
from agent_orchestrator.runtime.builtin_tools import TERMINAL_JOB_STATUSES
from agent_orchestrator.runtime.display_names import generate_agent_name
from agent_orchestrator.runtime.job_event_stream import JobEventStreamService
from agent_orchestrator.runtime.live_events import LiveEventBus
from agent_orchestrator.runtime.skills import (
    JOB_INLINE_SKILLS_KEY,
    MAX_INLINE_SKILLS,
    SkillRegistry,
    dedupe_skill_names,
)
from agent_orchestrator.schemas.jobs import (
    JobDetail,
    JobEventResponse,
    JobQuestionResponse,
    JobSummary,
    PromptRequest,
    QuestionAnswerRequest,
)
from agent_orchestrator.storage.repository import Repository

router = APIRouter(tags=["jobs"])


@router.post(
    "/sessions/{session_id}/prompts", status_code=202, operation_id="submit_prompt"
)
async def submit_prompt(
    request: Request,
    session_id: str,
    body: PromptRequest,
    repo: Repository = Depends(get_repository),
    registry: SkillRegistry = Depends(get_skill_registry),
) -> dict[str, JobSummary]:
    inline_skills = dedupe_skill_names(body.inline_skills)
    if len(inline_skills) > MAX_INLINE_SKILLS:
        raise HTTPException(
            status_code=400,
            detail=f"At most {MAX_INLINE_SKILLS} skills may be loaded into one prompt",
        )
    for skill_name in inline_skills:
        if registry.resolve(skill_name) is None:
            raise HTTPException(status_code=400, detail=f"Unknown skill '{skill_name}'")

    # The key is derived here, never taken from the caller's free-form metadata,
    # so a client cannot smuggle unvalidated skill names past the checks above.
    metadata = {
        key: value
        for key, value in body.metadata.items()
        if key != JOB_INLINE_SKILLS_KEY
    }
    if inline_skills:
        metadata[JOB_INLINE_SKILLS_KEY] = inline_skills

    # Read before enqueuing so "this is the session's first prompt" is decided
    # without counting the job we are about to add.
    session = await repo.get_session(session_id)
    _, prior_job_count = await repo.list_session_jobs(session_id, limit=1)

    try:
        item = await repo.enqueue_prompt_job(
            session_id,
            prompt=body.prompt,
            metadata_json=metadata,
            max_attempts=body.max_attempts
            or request.app.state.settings.default_job_max_attempts,
        )
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Terminated sessions cannot accept prompts"
        )
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # An unnamed session gets its name from the first prompt it is given: that is
    # the earliest moment there is anything to name it after. A session that
    # already carries a name — one its creator chose — is never renamed, and a
    # session that has run before is never renamed either.
    if (
        prior_job_count == 0
        and session is not None
        and not (session.name or "").strip()
    ):
        await repo.update_session(
            session_id, name=generate_agent_name(session_id, body.prompt)
        )

    return {"job": serialize_job(item)}


@router.get("/jobs/{job_id}", operation_id="get_job")
async def get_job(
    job_id: str,
    repo: Repository = Depends(get_repository),
    tool_catalog: McpToolCatalog = Depends(get_mcp_tool_catalog),
    skill_registry: SkillRegistry = Depends(get_skill_registry),
    live_event_bus: LiveEventBus = Depends(get_live_event_bus),
    item=Depends(require_job),
) -> dict[str, JobDetail]:
    events = await repo.list_events(job_id, after_id=0, limit=200)
    builtin_tools, mcp_tools = await list_effective_session_tools(
        mcp_tool_catalog=tool_catalog,
        skill_registry=skill_registry,
        repository=repo,
        live_event_bus=live_event_bus,
        session=item.session,
        is_master_job=item.parent_job_id is None and item.job_type == "prompt",
    )
    return {
        "job": serialize_job_detail(
            item,
            events,
            [
                *builtin_tools,
                *mcp_tools,
            ],
        )
    }


@router.get("/jobs/{job_id}/status", operation_id="get_job_status")
async def get_job_status(item=Depends(require_job)) -> dict[str, JobSummary]:
    return {"job": serialize_job(item)}


@router.post("/jobs/{job_id}/cancel", operation_id="cancel_job")
async def cancel_job(
    job_id: str, repo: Repository = Depends(get_repository)
) -> dict[str, JobSummary]:
    item = await repo.request_cancel(job_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job": serialize_job(item)}


@router.post(
    "/jobs/{job_id}/questions/{question_id}/answer", operation_id="answer_job_question"
)
async def answer_job_question(
    job_id: str,
    question_id: str,
    body: QuestionAnswerRequest,
    repo: Repository = Depends(get_repository),
    live_event_bus: LiveEventBus = Depends(get_live_event_bus),
    item=Depends(require_job),
) -> dict[str, JobQuestionResponse]:
    """Record the user's answer to a question the agent asked.

    The stored question is the authority for what may be answered: the submitted
    choice is matched against the choices the model actually offered, so a client
    can neither answer with something that was never on offer nor widen the set
    of answers the model asked for.
    """
    question = await repo.get_job_question(question_id)
    # Scoping the lookup to the path's job means a question cannot be answered
    # through some other job's URL.
    if question is None or question.job_id != job_id:
        raise HTTPException(status_code=404, detail="Question not found")

    if (body.choice_value is None) == (body.text is None):
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of 'choice_value' or 'text'",
        )

    if question.status != QUESTION_STATUS_PENDING:
        raise HTTPException(
            status_code=409,
            detail=(
                "This question has already been answered"
                if question.status == "answered"
                else "This question is no longer awaiting an answer"
            ),
        )
    # A job that has finished has nobody left waiting to read an answer. This is
    # what covers a run whose worker died without closing its question: the row
    # is still pending, but accepting an answer for it would be a lie.
    if item.status in TERMINAL_JOB_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="The job that asked this question has already finished",
        )

    if body.choice_value is not None:
        offered = {
            choice.get("value"): choice.get("label", "")
            for choice in question.choices_json or []
        }
        if body.choice_value not in offered:
            raise HTTPException(
                status_code=400, detail="That choice was not offered for this question"
            )
        answered = await repo.answer_job_question(
            question_id,
            source="choice",
            value=body.choice_value,
            label=offered[body.choice_value],
            text=None,
        )
    else:
        if not question.allow_free_text:
            raise HTTPException(
                status_code=400,
                detail="This question does not accept a free-text answer",
            )
        text = (body.text or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="'text' must not be empty")
        answered = await repo.answer_job_question(
            question_id, source="free_text", value=None, label=None, text=text
        )

    # None means the conditional update found nothing pending, so another writer
    # answered or closed the question between the check above and here.
    if answered is None:
        raise HTTPException(
            status_code=409, detail="This question is no longer awaiting an answer"
        )

    payload = {
        "question_id": answered.id,
        "source": answered.answer_source,
        "value": answered.answer_value,
        "label": answered.answer_label,
        "text": answered.answer_text,
    }
    await repo.append_event(
        job_id, answered.session_id, "user_question_answered", payload
    )
    await live_event_bus.publish(job_id, "user_question_answered", payload)
    return {"question": serialize_job_question(answered)}


@router.get("/jobs/{job_id}/events", operation_id="list_job_events")
async def list_job_events(
    job_id: str,
    after: int = 0,
    event_type: str | None = Query(default=None),
    repo: Repository = Depends(get_repository),
    item=Depends(require_job),
) -> dict[str, list[JobEventResponse]]:
    del item
    events = await repo.list_events(job_id, after_id=after)
    if event_type is not None:
        events = [event for event in events if event.event_type == event_type]
    return {"events": [serialize_event(event) for event in events]}


@router.get("/jobs/{job_id}/events/stream", operation_id="stream_job_events")
async def stream_job_events(
    request: Request,
    job_id: str,
    after: int = 0,
    job_event_stream: JobEventStreamService = Depends(get_job_event_stream),
    item=Depends(require_job),
) -> StreamingResponse:
    del item

    return StreamingResponse(
        job_event_stream.stream(
            job_id,
            after=after,
            is_disconnected=request.is_disconnected,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
