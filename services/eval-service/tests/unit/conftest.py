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
    *, game_id: str, seq: int, action: str = "play", reasoning: str = "because"
) -> StoredEvent:
    return make_event(
        game_id=game_id,
        seq=seq,
        actor="agent",
        event_type="move",
        payload={
            "intended_action": action,
            "reasoning": reasoning,
            "arguments": {"card_id": f"c{seq}"},
        },
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
    ):
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

    async def aclose(self) -> None:
        pass
