from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from eval_service.schema_migrations import ensure_schema
from eval_service.schemas.history import StoredEvent
from eval_service.storage.db import create_session_factory
from eval_service.storage.repository import Repository


@pytest_asyncio.fixture
async def repository():
    """A repository backed by a shared in-memory sqlite database."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    await ensure_schema(engine)
    factory = create_session_factory(engine)
    try:
        yield Repository(factory)
    finally:
        await engine.dispose()


def make_event(
    *,
    game_id: str,
    seq: int,
    actor: str,
    event_type: str = "event",
    payload: dict[str, Any] | None = None,
) -> StoredEvent:
    now = datetime.now(timezone.utc)
    return StoredEvent(
        event_id=f"evt-{seq}",
        game_id=game_id,
        seq=seq,
        envelope_version=1,
        actor=actor,
        event_type=event_type,
        payload=payload or {},
        occurred_at=now,
        recorded_at=now,
        idempotency_key=f"{game_id}:{actor}:{seq}",
    )


def state_event(
    *, game_id: str, seq: int, round_number: int, status: str = "in progress"
) -> StoredEvent:
    return make_event(
        game_id=game_id,
        seq=seq,
        actor="game-service",
        event_type="game_state",
        payload={
            "state": {"roundNumber": round_number, "mode": status},
            "status": status,
        },
    )


def agent_event(
    *,
    game_id: str,
    seq: int,
    action: str = "play",
    reasoning: str = "because",
    player: str | None = None,
    session_mode: str | None = None,
) -> StoredEvent:
    """A recorded agent move, shaped as the agent-orchestrator actually emits one.

    ``event_type`` is ``agent_move`` because that is the type the orchestrator
    writes — not an arbitrary agent event type. The distinction is load-bearing
    now that the ``agent`` actor also carries non-move events (``illegal_action``),
    and a fixture using a type nothing produces would test a predicate against a
    world that does not exist.

    ``player`` and ``session_mode`` are omitted from the payload unless supplied,
    matching the producer: a chat-mode session states neither.
    """
    payload: dict[str, Any] = {
        "intended_action": action,
        "reasoning": reasoning,
        "arguments": {"card_id": f"c{seq}"},
    }
    if session_mode is not None:
        payload["session_mode"] = session_mode
    if player is not None:
        payload["player"] = player
    return make_event(
        game_id=game_id,
        seq=seq,
        actor="agent",
        event_type="agent_move",
        payload=payload,
    )


def illegal_action_event(
    *,
    game_id: str,
    seq: int,
    player: str = "player1",
    violation: str = "played an ally with no resources paid",
    status: str = "open",
    resolution_note: str | None = None,
    required_undo: str = "return the ally to hand",
) -> StoredEvent:
    """An orchestrator-recorded illegal-action finding.

    An ``agent`` event that is NOT a move: history-service pins ``actor`` to a
    fixed literal set, so a new orchestrator concern arrives as a new event type
    under the existing actor.
    """
    payload: dict[str, Any] = {
        "player": player,
        "violation": violation,
        "required_undo": required_undo,
        "status": status,
        "session_mode": "orchestrated",
    }
    if resolution_note is not None:
        payload["resolution_note"] = resolution_note
    return make_event(
        game_id=game_id,
        seq=seq,
        actor="agent",
        event_type="illegal_action",
        payload=payload,
    )


class FakeHistoryClient:
    """In-memory stand-in for the history-service read + write-back API."""

    def __init__(self, events_by_game: dict[str, list[StoredEvent]] | None = None):
        self.events_by_game = events_by_game or {}
        self.written: list[tuple[str, dict[str, Any]]] = []
        self.healthy = True
        self.write_error: Exception | None = None

    async def list_all_events(self, game_id: str) -> list[StoredEvent]:
        return list(self.events_by_game.get(game_id, []))

    async def write_event(self, game_id: str, envelope: dict[str, Any]):
        if self.write_error is not None:
            raise self.write_error
        # Mimic history idempotency: store at most once per (game, key).
        key = envelope["idempotency_key"]
        if not any(
            g == game_id and e["idempotency_key"] == key for g, e in self.written
        ):
            self.written.append((game_id, envelope))
        return {"game_id": game_id, "seq": len(self.written), "inserted": True}

    async def health(self) -> bool:
        return self.healthy

    async def aclose(self) -> None:
        pass


class StubJudgeClient:
    """A judge client that returns a canned verdict, or fails, on demand."""

    def __init__(
        self,
        *,
        verdict: dict[str, Any] | None = None,
        fail_times: int = 0,
        error: Exception | None = None,
        judge_key_providers: frozenset[str] | None = None,
    ):
        self.judge_key_providers = judge_key_providers
        self.verdict = verdict or {
            "scores": {
                "rules_legality": 8,
                "strategic_quality": 6,
                "tempo_efficiency": 7,
                "threat_resource": 7,
            },
            "overall_score": 7,
            "rationale": "Solid play.",
            "flags": [],
        }
        self.fail_times = fail_times
        self.error = error
        self.calls: list[dict[str, Any]] = []
        self.healthy = True

    async def judge(self, *, model, messages, max_tokens, gateway_options=None) -> str:
        self.calls.append(
            {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "gateway_options": gateway_options,
            }
        )
        if self.error is not None:
            raise self.error
        if self.fail_times > 0:
            self.fail_times -= 1
            from eval_service.integrations.bifrost import BifrostError

            raise BifrostError("gateway_error", "boom", retryable=True)
        return json.dumps(self.verdict)

    async def health(self) -> bool:
        return self.healthy

    async def named_key_providers(self, key_name: str) -> frozenset[str] | None:
        """Providers with a judge key entry, or ``None`` for "cannot tell"."""
        return self.judge_key_providers

    async def aclose(self) -> None:
        pass
