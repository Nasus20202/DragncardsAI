from __future__ import annotations

from eval_service.integrations.history import HistoryClient
from eval_service.judge.assembly import detect_round_boundaries
from eval_service.judge.events import is_agent_move
from eval_service.judge.rounds import round_label
from eval_service.runtime.players import players_in_span
from eval_service.schemas.api import RoundListResponse, RoundSummary
from eval_service.schemas.history import PLATFORM_DRAGNCARDS, Platform, StoredEvent


class RoundsService:
    """Lists the rounds the eval-service detects for a game.

    Exists so a client can select a ROUND without naming a sequence inside it.
    Boundaries are detected here, by the same code that assembles a round
    roll-up, rather than re-derived by the client: a round this listing reports is
    by construction a round the service can grade, and the two cannot drift apart.
    """

    def __init__(self, *, history: HistoryClient):
        self._history = history

    async def list_rounds(
        self, game_id: str, platform: Platform = PLATFORM_DRAGNCARDS
    ) -> RoundListResponse:
        """Detected rounds for ``game_id``, in sequence order.

        Raises :class:`GameNotFoundError` when the game has no recorded events, so
        "this game does not exist" is not reported as "this game has no rounds".
        """
        # Imported here to avoid importing the request service (and its judge
        # config machinery) just for one exception type.
        from eval_service.runtime.requests import GameNotFoundError

        try:
            events = await self._history.list_all_events(game_id, platform)
        except TypeError:
            # Keep lightweight test/downgrade clients that predate the optional
            # platform selector usable; the history default is DragnCards.
            events = await self._history.list_all_events(game_id)
        if not events:
            raise GameNotFoundError(f"no events recorded for game {game_id!r}")
        return RoundListResponse(
            game_id=game_id,
            rounds=[
                _summarize(events, round_of_play, from_seq, to_seq)
                for round_of_play, from_seq, to_seq in detect_round_boundaries(events)
            ],
        )


def _summarize(
    events: list[StoredEvent], round_of_play: int, from_seq: int, to_seq: int
) -> RoundSummary:
    move_seqs = [
        e.seq for e in events if is_agent_move(e) and from_seq <= e.seq <= to_seq
    ]
    return RoundSummary(
        round_number=round_of_play,
        label=round_label(round_of_play),
        from_seq=from_seq,
        to_seq=to_seq,
        move_count=len(move_seqs),
        players=players_in_span(events, from_seq, to_seq) if move_seqs else [],
    )
