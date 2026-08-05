from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import uuid4

from eval_service.config import Settings
from eval_service.integrations.history import HistoryClient
from eval_service.judge.assembly import detect_round_boundaries
from eval_service.judge.config import (
    SkillResolver,
    SkillReferenceError,
    UnknownSkillError,
    resolve_judge_config,
)
from eval_service.judge.events import is_agent_move
from eval_service.runtime.inflight import InflightRegistry
from eval_service.runtime.players import attribute_move, players_in_span
from eval_service.schemas.api import (
    CreateEvaluationResponse,
    EvaluationRequestBody,
    Selection,
    TargetSummary,
)
from eval_service.schemas.history import StoredEvent
from eval_service.storage.repository import Repository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlannedTarget:
    """One concrete target the cascade will claim.

    ``scope`` may differ from the request's scope: a round/game request fans out
    into the move/round targets it depends on. ``player`` is the seat this target
    scores (a move's acting player, or the per-player round/game roll-up seat).
    """

    target_seq: int
    scope: str
    player: str
    round_span: tuple[int, int] | None = None


class RequestError(Exception):
    """Client-correctable request error (maps to 400)."""


class GameNotFoundError(Exception):
    """No events recorded for the game (maps to 404)."""


class RequestService:
    """Expands a selection into concrete targets and claims them idempotently."""

    def __init__(
        self,
        *,
        settings: Settings,
        repository: Repository,
        history: HistoryClient,
        skill_resolver: SkillResolver | None = None,
        inflight: InflightRegistry | None = None,
    ):
        self._settings = settings
        self._repository = repository
        self._history = history
        self._skill_resolver = skill_resolver or SkillResolver(
            settings.skill_root_paths
        )
        # Transient in-flight task registry, shared with the worker, so a force
        # re-claim can abort any evaluation already running for a target.
        self._inflight = inflight

    async def create(
        self, game_id: str, body: EvaluationRequestBody
    ) -> CreateEvaluationResponse:
        # Resolve + validate the per-evaluation judge config FIRST so an unknown
        # skill, an unresolvable/over-budget skill reference, or any other
        # config error rejects the request with a 400 before any target is
        # enqueued.
        try:
            resolved = resolve_judge_config(
                self._settings, body.judge, self._skill_resolver
            )
        except (UnknownSkillError, SkillReferenceError) as exc:
            raise RequestError(str(exc)) from exc
        judge_config = resolved.to_json()

        events = await self._history.list_all_events(game_id)
        if not events:
            raise GameNotFoundError(f"no events recorded for game {game_id!r}")

        targets = self._expand(body.scope, body.selection, events)
        if not targets:
            raise RequestError("selection expanded to no valid targets for this game")

        cap = self._settings.eval_max_targets_per_request
        if len(targets) > cap:
            raise RequestError(
                f"selection expands to {len(targets)} targets, exceeding the "
                f"per-request limit of {cap}; narrow the selection"
            )

        request_id = str(uuid4())
        await self._repository.create_request(
            request_id=request_id,
            game_id=game_id,
            scope=body.scope,
            selection=body.selection.model_dump(),
            force=body.force,
            judge_config=judge_config,
        )

        summaries: list[TargetSummary] = []
        created = 0
        skipped = 0
        for planned in targets:
            claim = await self._repository.claim_target(
                request_id=request_id,
                game_id=game_id,
                target_seq=planned.target_seq,
                scope=planned.scope,
                round_span=planned.round_span,
                force=body.force,
                judge_config=judge_config,
                player=planned.player,
            )
            if claim.claimed:
                # A force re-claim resets the row from ``running`` back to
                # ``pending``; abort any task still evaluating this target so a
                # stale in-flight evaluation cannot write a second verdict
                # alongside the fresh one the next drain will produce. Mirrors
                # the cancel route (durable state changed first, then abort the
                # task). There is no ``await`` between ``claim_target`` returning
                # and this cancel, so the worker cannot re-claim the row in
                # between and only one evaluation of a target is ever in flight.
                if body.force and self._inflight is not None and claim.target_id:
                    self._inflight.cancel(claim.target_id)
                created += 1
                status = "pending"
            else:
                skipped += 1
                status = claim.existing_status or "completed"
            summaries.append(
                TargetSummary(
                    target_seq=planned.target_seq,
                    scope=planned.scope,  # type: ignore[arg-type]
                    round_span=list(planned.round_span) if planned.round_span else None,
                    player=planned.player or None,
                    status=status,  # type: ignore[arg-type]
                )
            )

        return CreateEvaluationResponse(
            request_id=request_id,
            game_id=game_id,
            scope=body.scope,
            created_count=created,
            skipped_count=skipped,
            targets=summaries,
        )

    def _expand(
        self, scope: str, selection: Selection, events: list[StoredEvent]
    ) -> list[PlannedTarget]:
        """Expand a request into its full, deduplicated cascade of targets.

        A ``move`` request yields per-move targets (each per its acting player).
        A ``round`` request additionally claims the move targets each round
        depends on, plus one round target per acting player. A ``game`` request
        claims the whole game's moves, all per-player round roll-ups, and one
        per-player game roll-up — so a single request fans out across the entire
        subtree it requires. Ordering is move → round → game so lower levels are
        drained (and graded) before the roll-ups that depend on them.
        """
        if scope == "move":
            return self._plan_moves(self._selected_move_seqs(selection, events), events)
        if scope == "round":
            spans = self._selected_round_spans(selection, events)
            return self._plan_for_spans(events, spans, top_scope="round")
        # scope == "game"
        spans = [b[1:] for b in detect_round_boundaries(events)]
        return self._plan_for_spans(events, spans, top_scope="game")

    def _selected_move_seqs(
        self, selection: Selection, events: list[StoredEvent]
    ) -> list[int]:
        agent_seqs = {e.seq for e in events if is_agent_move(e)}
        chosen: set[int] = set()
        if selection.whole_game:
            chosen |= agent_seqs
        if selection.seqs:
            chosen |= {s for s in selection.seqs if s in agent_seqs}
        if selection.seq_range:
            lo, hi = selection.seq_range.from_seq, selection.seq_range.to_seq
            chosen |= {s for s in agent_seqs if lo <= s <= hi}
        return sorted(chosen)

    def _plan_moves(
        self, seqs: list[int], events: list[StoredEvent]
    ) -> list[PlannedTarget]:
        return [
            PlannedTarget(
                target_seq=seq,
                scope="move",
                player=attribute_move(events, seq),
            )
            for seq in seqs
        ]

    def _selected_round_spans(
        self, selection: Selection, events: list[StoredEvent]
    ) -> list[tuple[int, int]]:
        boundaries = detect_round_boundaries(events)
        # ``selection.rounds`` names rounds of PLAY (1-based), the same numbers the
        # History UI shows -- NOT the raw DragnCards ``roundNumber``, which counts
        # completed rounds and is 0 for the first round of play.
        by_round = {b[0]: b for b in boundaries}
        chosen: dict[int, tuple[int, int]] = {}

        def containing_round(seq: int) -> tuple[int, int, int] | None:
            for b in boundaries:
                if b[1] <= seq <= b[2]:
                    return b
            return None

        if selection.whole_game:
            for _rn, frm, to in boundaries:
                chosen[to] = (frm, to)
        if selection.rounds:
            for rn in selection.rounds:
                b = by_round.get(rn)
                if b is not None:
                    chosen[b[2]] = (b[1], b[2])
        if selection.seqs:
            # A selected seq maps to the round that CONTAINS it (not only an
            # exact round-closing seq), so a mid-round move resolves to its
            # round rather than silently expanding to nothing.
            for seq in selection.seqs:
                b = containing_round(seq)
                if b is not None:
                    chosen[b[2]] = (b[1], b[2])
        if selection.seq_range:
            lo, hi = selection.seq_range.from_seq, selection.seq_range.to_seq
            for _rn, frm, to in boundaries:
                if frm <= hi and to >= lo:
                    chosen[to] = (frm, to)
        return [chosen[to] for to in sorted(chosen)]

    def _plan_for_spans(
        self,
        events: list[StoredEvent],
        spans: list[tuple[int, int]],
        *,
        top_scope: str,
    ) -> list[PlannedTarget]:
        """Build the move → round (→ game) cascade for the given round spans.

        Move targets come first (their acting player), then one round target per
        acting player for each span, then — for a game request — one game target
        per acting player across all spans.
        """
        move_targets: list[PlannedTarget] = []
        round_targets: list[PlannedTarget] = []
        seen_moves: set[int] = set()

        for frm, to in spans:
            for seq in self._agent_seqs_in_span(events, frm, to):
                if seq not in seen_moves:
                    seen_moves.add(seq)
                    move_targets.append(
                        PlannedTarget(
                            target_seq=seq,
                            scope="move",
                            player=attribute_move(events, seq),
                        )
                    )
            for player in players_in_span(events, frm, to):
                round_targets.append(
                    PlannedTarget(
                        target_seq=to,
                        scope="round",
                        player=player,
                        round_span=(frm, to),
                    )
                )

        plan = move_targets + round_targets
        if top_scope == "game" and spans:
            game_from = min(frm for frm, _to in spans)
            game_to = max(to for _frm, to in spans)
            for player in players_in_span(events, game_from, game_to):
                plan.append(
                    PlannedTarget(
                        target_seq=game_to,
                        scope="game",
                        player=player,
                        round_span=(game_from, game_to),
                    )
                )
        return plan

    @staticmethod
    def _agent_seqs_in_span(
        events: list[StoredEvent], from_seq: int, to_seq: int
    ) -> list[int]:
        return sorted(
            e.seq for e in events if is_agent_move(e) and from_seq <= e.seq <= to_seq
        )
