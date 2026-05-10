from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from agent_orchestrator.api.deps import get_mcp_tool_catalog, get_repository, require_job
from agent_orchestrator.api.serializers import serialize_event, serialize_job, serialize_job_detail
from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
from agent_orchestrator.schemas.jobs import JobDetail, JobEventResponse, JobSummary, PromptRequest
from agent_orchestrator.storage.repository import Repository

router = APIRouter(tags=["jobs"])


@router.post("/sessions/{session_id}/prompts", status_code=202)
async def submit_prompt(
    request: Request,
    session_id: str,
    body: PromptRequest,
    repo: Repository = Depends(get_repository),
) -> dict[str, JobSummary]:
    try:
        item = await repo.enqueue_prompt_job(
            session_id,
            prompt=body.prompt,
            metadata_json=body.metadata,
            max_attempts=body.max_attempts or request.app.state.settings.default_job_max_attempts,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Terminated sessions cannot accept prompts")
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"job": serialize_job(item)}


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    repo: Repository = Depends(get_repository),
    tool_catalog: McpToolCatalog = Depends(get_mcp_tool_catalog),
    item=Depends(require_job),
) -> dict[str, JobDetail]:
    events = await repo.list_events(job_id, after_id=0, limit=200)
    tools = await tool_catalog.list_session_tools(item.session.mcp_assignments)
    return {"job": serialize_job_detail(item, events, tools)}


@router.get("/jobs/{job_id}/status")
async def get_job_status(item=Depends(require_job)) -> dict[str, JobSummary]:
    return {"job": serialize_job(item)}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, repo: Repository = Depends(get_repository)) -> dict[str, JobSummary]:
    item = await repo.request_cancel(job_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job": serialize_job(item)}


@router.get("/jobs/{job_id}/events")
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


@router.get("/jobs/{job_id}/events/stream")
async def stream_job_events(
    request: Request,
    job_id: str,
    after: int = 0,
    repo: Repository = Depends(get_repository),
    item=Depends(require_job),
) -> StreamingResponse:
    del item

    async def event_source():
        cursor = after
        while True:
            events = await repo.list_events(job_id, after_id=cursor)
            for event in events:
                cursor = event.id
                payload = serialize_event(event).model_dump(mode="json")
                yield f"id: {event.id}\nevent: {event.event_type}\ndata: {json.dumps(payload)}\n\n"
            job = await repo.get_job(job_id)
            if job is None:
                return
            if await request.is_disconnected():
                return
            if job.status in {"completed", "failed", "cancelled"} and not events:
                return
            await asyncio.sleep(request.app.state.settings.worker_poll_interval_seconds)

    return StreamingResponse(event_source(), media_type="text/event-stream")
