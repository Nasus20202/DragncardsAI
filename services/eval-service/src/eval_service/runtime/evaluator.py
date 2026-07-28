from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from eval_service.config import Settings
from eval_service.integrations.bifrost import BifrostError, BifrostJudgeClient
from eval_service.integrations.history import HistoryClient
from eval_service.judge.actions import non_strategic_reason
from eval_service.judge.assembly import (
    BoundaryUndetectedError,
    assemble_game_input,
    assemble_move_input,
    assemble_round_input,
)
from eval_service.judge.config import (
    ResolvedJudgeConfig,
    ResolvedReasoning,
    SkillResolver,
    provider_from_model,
)
from eval_service.judge.parse import VerdictParseError, parse_verdict
from eval_service.judge.prompt import (
    build_game_messages,
    build_move_messages,
    build_round_messages,
)
from eval_service.judge.writeback import build_verdict_envelope
from eval_service.schemas.history import StoredEvent
from eval_service.schemas.verdict import VerdictPayload
from eval_service.storage.repository import Repository

logger = logging.getLogger(__name__)

# Callback invoked with each incremental judge text delta (for SSE token push).
TokenSink = Callable[[str], Awaitable[None]]
# Callback invoked with the detail of a failure hit DURING an evaluation (a judge
# attempt that will be retried), so live subscribers learn about it as it happens
# rather than only at the terminal transition. The detail is already durable on
# the target row by the time the sink runs.
ErrorSink = Callable[[str], Awaitable[None]]


class JudgeNotConfiguredError(Exception):
    """Raised when no judge model is configured; evaluation must be refused."""


class JudgeAttemptsExhaustedError(Exception):
    """Raised when every judge attempt failed, carrying the LAST gateway error.

    The message is recorded as the target's skip reason so a definitive
    misconfiguration -- notably Bifrost's ``no supported key found with name
    "eval-judge" for provider: <p>`` when that provider has no dedicated judge
    key -- is visible on the target instead of a generic "judge failed".
    """


class Evaluator:
    """Evaluates a single claimed target: assemble -> judge -> write back.

    Failure isolation: a judge call is retried with bounded backoff up to the
    configured attempt limit, then the target is marked FAILED with the reason so
    one failing target never blocks the rest. The bookkeeping record is
    finalized to ``completed`` only AFTER a successful history write-back.

    Errors are reported as they happen, not only at the end: every failed attempt
    is recorded on the target row (Postgres) while the target is still ``running``
    and pushed through ``on_error``, so a retry storm or a definitive
    misconfiguration is visible during the run. ``skipped`` is reserved for a
    DELIBERATE skip (a non-strategic action, which carries no decision to grade)
    so a client can never mistake an error for a designed skip.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        repository: Repository,
        history: HistoryClient,
        judge: BifrostJudgeClient,
        skill_resolver: SkillResolver | None = None,
    ):
        self._settings = settings
        self._repository = repository
        self._history = history
        self._judge = judge
        self._skill_resolver = skill_resolver or SkillResolver(
            settings.skill_root_paths
        )

    def _default_config(self) -> ResolvedJudgeConfig:
        """The effective config used when a target carries no per-request one."""
        return ResolvedJudgeConfig(
            model=self._settings.eval_judge_model,
            provider=self._settings.eval_judge_provider
            or provider_from_model(self._settings.eval_judge_model),
            reasoning=ResolvedReasoning(
                enabled=self._settings.eval_judge_reasoning_enabled,
                effort=self._settings.eval_judge_reasoning_effort,
                max_tokens=None,
            ),
            prompt_override=None,
            skills=(),
        )

    async def evaluate_target(
        self,
        *,
        target_id: int,
        game_id: str,
        target_seq: int,
        scope: str,
        events: list[StoredEvent],
        player: str | None = None,
        judge_config: ResolvedJudgeConfig | None = None,
        on_token: TokenSink | None = None,
        on_error: ErrorSink | None = None,
    ) -> bool:
        """Evaluate one claimed target. Returns whether it made PROGRESS.

        ``False`` means one thing only: this is a round/game roll-up that was
        re-deferred to ``pending`` because the children it depends on are still in
        flight. Every other outcome -- a verdict, a deliberate skip, a failure, a
        write-back abandoned to a cancellation -- is progress. The worker uses this
        to tell a productive drain cycle from one that merely re-queued roll-ups,
        so it can wait instead of hot-looping on the database while the children
        are graded.
        """
        # The target arrives already claimed as ``running`` by the worker, so
        # all transitions below are conditional on it still being running: a
        # concurrent force re-claim (which resets the row to ``pending`` under a
        # new claim) is therefore never clobbered by this stale evaluation. The
        # same guard means a cancel (which sets the row to ``cancelled``) is
        # never clobbered by a stale finalize.
        config = judge_config or self._default_config()

        if not config.model.strip():
            await self._repository.mark_failed(
                target_id,
                "no judge model configured (EVAL_JUDGE_MODEL unset)",
            )
            raise JudgeNotConfiguredError(
                "EVAL_JUDGE_MODEL is not configured; refusing to evaluate"
            )

        # Non-strategic actions carry no decision a judge can grade (a card search
        # cannot be a wrong play; taking a card into hand can be). Record them as
        # SKIPPED with the reason -- the same per-target skip channel a judge
        # failure uses -- so a skipped action is never mistaken for a passed one,
        # and no judge call is spent on it.
        if scope == "move":
            reason = self._non_strategic_reason(events, target_seq)
            if reason is not None:
                await self._repository.mark_skipped(target_id, reason)
                return True

        # Dependency gate: a round/game roll-up SHALL NOT be produced until every
        # lower-level child it depends on is graded. While any child is still in
        # flight, re-defer this target to ``pending`` so a later drain retries it
        # against complete child context. Children eventually reach a terminal
        # state, so the deferral always terminates.
        if scope in ("round", "game"):
            deferred = await self._defer_if_children_pending(
                target_id=target_id,
                game_id=game_id,
                target_seq=target_seq,
                scope=scope,
                events=events,
            )
            if deferred:
                return False
            # Re-read the latest history so the roll-up sees child verdicts that
            # earlier-completed targets in this cascade just wrote back.
            events = await self._latest_events(game_id, events)

        # Every branch below is an ERROR, not a skip: it is recorded as ``failed``
        # with its reason so the UI can show what went wrong, and so it is never
        # conflated with the deliberate non-strategic skip above.
        try:
            verdict = await self._produce_verdict(
                target_id=target_id,
                game_id=game_id,
                target_seq=target_seq,
                scope=scope,
                events=events,
                player=player,
                config=config,
                on_token=on_token,
                on_error=on_error,
            )
        except BoundaryUndetectedError as exc:
            await self._fail(target_id, f"boundary undetected: {exc}", on_error)
            return True
        except ValueError as exc:
            await self._fail(target_id, f"assembly error: {exc}", on_error)
            return True
        except JudgeAttemptsExhaustedError as exc:
            await self._fail(
                target_id, f"judge failed after retry limit: {exc}", on_error
            )
            return True

        if verdict is None:
            # Defensive: exhausted retries raise JudgeAttemptsExhaustedError above
            # (with the gateway's reason), so this only guards a verdict-less
            # return that no current path produces.
            await self._fail(target_id, "judge failed after retry limit", on_error)
            return True

        # Re-check the durable status IMMEDIATELY before writing back: a cancel
        # (or a concurrent force re-claim) that landed after this target was
        # claimed ``running`` but before the registry could abort the in-flight
        # task must not leave a stale verdict in history. If the row is no
        # longer ``running`` the cancellation/re-claim owns it, so we abort the
        # write-back and leave the durable status untouched.
        current = await self._repository.get_target_status(target_id)
        if current != "running":
            logger.info(
                "Skipping verdict write-back for game=%s seq=%s scope=%s: "
                "target is %r, not running (cancelled or re-claimed)",
                game_id,
                target_seq,
                scope,
                current,
            )
            # The cancellation / re-claim already moved the row to a terminal (or
            # freshly-pending) state of its own, so this cycle is not idle.
            return True

        # Write back BEFORE finalizing the bookkeeping record.
        envelope = build_verdict_envelope(game_id, verdict, config)
        try:
            await self._history.write_event(game_id, envelope)
        except Exception as exc:  # noqa: BLE001 - write-back failure -> skip
            logger.warning(
                "verdict write-back failed for game=%s seq=%s scope=%s: %s",
                game_id,
                target_seq,
                scope,
                exc,
            )
            await self._fail(target_id, f"write-back failed: {exc}", on_error)
            return True

        await self._repository.finalize_completed(target_id, verdict.model_dump())
        return True

    async def _fail(
        self, target_id: int, detail: str, on_error: ErrorSink | None
    ) -> None:
        """Mark a target ``failed`` with its reason and push the reason live."""
        await self._repository.mark_failed(target_id, detail)
        if on_error is not None:
            await on_error(detail)

    async def _report_attempt_error(
        self, target_id: int, detail: str, on_error: ErrorSink | None
    ) -> None:
        """Surface a failure hit mid-evaluation, while the target keeps running.

        The detail is written to the target row in Postgres (durable, readable by
        any poller or a stream re-reading the snapshot) and pushed through the
        live sink, so a failed attempt is reported as it happens instead of being
        logged and forgotten with only the LAST one surviving to the terminal row.
        """
        await self._repository.record_attempt_error(target_id, detail)
        if on_error is not None:
            await on_error(detail)

    async def _produce_verdict(
        self,
        *,
        target_id: int,
        game_id: str,
        target_seq: int,
        scope: str,
        events: list[StoredEvent],
        player: str | None,
        config: ResolvedJudgeConfig,
        on_token: TokenSink | None,
        on_error: ErrorSink | None = None,
    ) -> VerdictPayload | None:
        """Assemble input, call the judge with retry, and parse a verdict.

        Returns None when the judge keeps failing up to the attempt limit.
        """
        # Resolve selected skills to markdown (validated already at request time;
        # re-resolved here so the worker injects the same content).
        skills = self._skill_resolver.load_markdown(config.skills)

        if scope == "move":
            # A move is graded in the context of ITS ROUND: the assembly resolves
            # the containing round and attaches that round's other moves either
            # side. The two settings are backstops on a pathological round, not
            # the window itself.
            move = assemble_move_input(
                events,
                target_seq,
                context_before=self._settings.eval_judge_move_context_before,
                context_after=self._settings.eval_judge_move_context_after,
            )
            messages = build_move_messages(
                move,
                prompt_override=config.prompt_override,
                skills=skills,
                max_state_chars=self._settings.eval_judge_max_state_chars,
                max_context_reasoning_chars=(
                    self._settings.eval_judge_move_context_reasoning_chars
                ),
            )
            round_span = None
        elif scope == "game":
            game = assemble_game_input(
                events,
                target_seq,
                from_seq=self._game_from_seq(events),
                player=player,
            )
            messages = build_game_messages(
                game,
                prompt_override=config.prompt_override,
                skills=skills,
                max_state_chars=self._settings.eval_judge_max_state_chars,
            )
            round_span = [game.from_seq, game.to_seq]
        else:
            rnd = assemble_round_input(
                events,
                target_seq,
                player=player,
                skip_actions=self._settings.non_strategic_actions,
            )
            messages = build_round_messages(
                rnd,
                prompt_override=config.prompt_override,
                skills=skills,
                max_state_chars=self._settings.eval_judge_max_state_chars,
                max_round_moves=self._settings.eval_judge_max_round_moves,
            )
            round_span = [rnd.from_seq, rnd.to_seq]

        gateway_options = config.reasoning.to_gateway_options()

        attempt = 0
        while attempt < self._settings.eval_max_attempts:
            attempt += 1
            try:
                # Only forward live tokens on the FIRST attempt: a retry would
                # otherwise stream a second copy of the text into the SSE view
                # (which concatenates deltas) with no reset signal.
                response_text = await self._call_judge(
                    config=config,
                    messages=messages,
                    gateway_options=gateway_options,
                    on_token=on_token if attempt == 1 else None,
                )
                return parse_verdict(
                    response_text,
                    scope=scope,  # type: ignore[arg-type]
                    target_seq=target_seq,
                    round_span=round_span,
                    player=player,
                    # Record the ACTUAL model/provider used for this evaluation.
                    model=config.model,
                    provider=config.provider,
                    evaluator_version=self._settings.evaluator_version,
                )
            except (BifrostError, VerdictParseError) as exc:
                logger.info(
                    "judge attempt %d/%d failed for game=%s seq=%s: %s",
                    attempt,
                    self._settings.eval_max_attempts,
                    game_id,
                    target_seq,
                    exc,
                )
                # Report the attempt failure NOW rather than only when the target
                # reaches a terminal state: without this, the first attempts of a
                # retry storm were logged and dropped, and the user saw nothing
                # until the run finished (and then only the last error).
                await self._report_attempt_error(
                    target_id,
                    f"judge attempt {attempt}/{self._settings.eval_max_attempts} "
                    f"failed: {exc}",
                    on_error,
                )
                # Honor the gateway's retryability signal: a non-retryable
                # BifrostError (e.g. a 4xx that won't change on a retry) fails
                # fast without burning further attempts or backoff.
                if isinstance(exc, BifrostError) and not exc.retryable:
                    raise JudgeAttemptsExhaustedError(str(exc)) from exc
                if attempt >= self._settings.eval_max_attempts:
                    raise JudgeAttemptsExhaustedError(str(exc)) from exc
                await asyncio.sleep(self._settings.eval_retry_backoff_seconds * attempt)
        return None

    async def _call_judge(
        self,
        *,
        config: ResolvedJudgeConfig,
        messages: list[dict[str, str]],
        gateway_options: dict[str, object],
        on_token: TokenSink | None,
    ) -> str:
        """Call the judge, streaming tokens when a sink is provided.

        Falls back to the non-streaming path when no sink is given (tests) or
        when the client doesn't expose a streaming method.
        """
        stream = getattr(self._judge, "judge_stream", None)
        if on_token is not None and stream is not None:
            parts: list[str] = []
            async for delta in stream(
                model=config.model,
                messages=messages,
                max_tokens=self._settings.eval_judge_max_tokens,
                gateway_options=gateway_options or None,
            ):
                if delta:
                    parts.append(delta)
                    await on_token(delta)
            return "".join(parts)
        return await self._judge.judge(
            model=config.model,
            messages=messages,
            max_tokens=self._settings.eval_judge_max_tokens,
            gateway_options=gateway_options or None,
        )

    def _non_strategic_reason(
        self, events: list[StoredEvent], target_seq: int
    ) -> str | None:
        """The skip reason for a non-strategic move, or None to evaluate it.

        Conservative in both directions: a target whose event is missing (or is
        not an agent move) is left to the normal assembly path, which reports the
        real problem, rather than being written off as non-strategic.
        """
        event = next((e for e in events if e.seq == target_seq), None)
        if event is None or event.actor != "agent":
            return None
        reason = non_strategic_reason(
            event.payload.get("intended_action"),
            self._settings.non_strategic_actions,
        )
        if reason is None:
            return None
        action = event.payload.get("intended_action")
        return f"non-strategic action {action!r}: {reason}"

    async def _defer_if_children_pending(
        self,
        *,
        target_id: int,
        game_id: str,
        target_seq: int,
        scope: str,
        events: list[StoredEvent],
    ) -> bool:
        """Re-defer a round/game target while its children are still in flight.

        A round depends on the move targets in its span; a game depends on the
        round targets across the whole game. The dependency window is derived
        from recorded history (round boundaries), and the child completion state
        is read from Postgres — no in-memory dependency graph. Returns whether
        the target was re-deferred to ``pending``.
        """
        if scope == "round":
            from_seq, to_seq = self._round_span(events, target_seq)
            child_scope = "move"
        else:  # game
            from_seq, to_seq = self._game_from_seq(events), target_seq
            child_scope = "round"

        pending = await self._repository.count_nonterminal_children(
            game_id=game_id,
            from_seq=from_seq,
            to_seq=to_seq,
            child_scope=child_scope,
        )
        if pending > 0:
            return await self._repository.defer_to_pending(target_id)
        return False

    async def _latest_events(
        self, game_id: str, fallback: list[StoredEvent]
    ) -> list[StoredEvent]:
        """Re-read history so a roll-up sees freshly-written child verdicts."""
        try:
            return await self._history.list_all_events(game_id)
        except Exception as exc:  # noqa: BLE001 - fall back to the batch snapshot
            logger.info(
                "Failed to re-read history for roll-up game=%s: %s", game_id, exc
            )
            return fallback

    @staticmethod
    def _round_span(events: list[StoredEvent], closing_seq: int) -> tuple[int, int]:
        from eval_service.judge.assembly import detect_round_boundaries

        for _rn, frm, to in detect_round_boundaries(events):
            if to == closing_seq:
                return frm, to
        return closing_seq, closing_seq

    @staticmethod
    def _game_from_seq(events: list[StoredEvent]) -> int:
        seqs = [e.seq for e in events]
        return min(seqs) if seqs else 1
