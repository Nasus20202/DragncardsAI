"""The history-service's telemetry must actually be wired, not merely available.

DRA-23: the service shipped with the OTEL_* environment variables set in
`docker-compose.yaml` but no instrumentation anywhere in its code, so nothing was
ever exported. These tests pin the code-level wiring — the identity, the app
edge, the database edge and the Valkey edge — because that is the part that was
missing and the part a configuration review cannot catch.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dragncards_common import telemetry as shared_telemetry

import history_service.telemetry as telemetry
from history_service.config import Settings
from history_service.runtime.app import create_app
from history_service.storage.db import create_engine
from history_service.storage.valkey import RespConnection


@pytest.fixture(autouse=True)
def reset_telemetry_globals():
    shared_telemetry._runtime = None
    shared_telemetry._httpx_instrumented = False
    shared_telemetry._logging_patched = False
    shared_telemetry._sqlalchemy_instrumented = False
    yield
    shared_telemetry._runtime = None
    shared_telemetry._httpx_instrumented = False
    shared_telemetry._logging_patched = False
    shared_telemetry._sqlalchemy_instrumented = False


def test_service_identity_defaults_to_history_service(monkeypatch):
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)

    config = telemetry.TelemetryConfig.from_env(telemetry.DEFAULT_SERVICE_NAME)

    assert telemetry.DEFAULT_SERVICE_NAME == "history-service"
    assert config.service_name == "history-service"


def test_setup_telemetry_passes_the_service_name_to_the_shared_bootstrap(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(
        shared_telemetry,
        "setup_telemetry",
        lambda name: seen.append(name) or "runtime",
    )

    assert telemetry.setup_telemetry() == "runtime"
    assert seen == ["history-service"]


def test_main_initializes_telemetry_before_serving(monkeypatch):
    """The bootstrap has to run in the entrypoint, not just be importable."""
    from history_service import main as main_module

    calls: list[str] = []
    monkeypatch.setattr(
        main_module, "setup_telemetry", lambda: calls.append("setup_telemetry")
    )
    monkeypatch.setattr(
        main_module, "create_app", lambda settings: calls.append("create_app")
    )
    monkeypatch.setattr(main_module, "mount_mcp", lambda app: calls.append("mount_mcp"))
    monkeypatch.setattr(
        main_module.uvicorn, "run", lambda app, host, port: calls.append("run")
    )

    main_module.main()

    assert calls == ["setup_telemetry", "create_app", "mount_mcp", "run"]


def test_create_app_instruments_the_server_edge(monkeypatch):
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
    instrumentor = MagicMock()
    monkeypatch.setattr(shared_telemetry, "_fastapi_instrumentor", lambda: instrumentor)
    monkeypatch.setattr(
        shared_telemetry, "setup_telemetry", lambda name: SimpleNamespace(enabled=True)
    )

    app = create_app(start_ingester=False)

    instrumentor.instrument_app.assert_called_once_with(app)
    assert app.state._otel_instrumented is True


def test_create_app_skips_instrumentation_when_sdk_disabled(monkeypatch):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")

    app = create_app(start_ingester=False)

    assert getattr(app.state, "_otel_instrumented", False) is False


def test_create_engine_instruments_the_database_edge(monkeypatch):
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    instrumentor_instance = MagicMock()
    monkeypatch.setattr(
        shared_telemetry,
        "_sqlalchemy_instrumentor",
        lambda: lambda: instrumentor_instance,
    )
    monkeypatch.setattr(
        shared_telemetry, "setup_telemetry", lambda name: SimpleNamespace(enabled=True)
    )

    engine = create_engine("sqlite+aiosqlite:///:memory:")

    instrumentor_instance.instrument.assert_called_once_with(engine=engine.sync_engine)


def test_valkey_client_carries_a_tracer_so_resp_spans_are_emitted():
    """The shared RESP client is silent unless it is handed a tracer."""
    conn = RespConnection.from_url("redis://localhost:6381/0")

    assert conn._tracer is not None


class _RecordingSpan:
    def __init__(self, attributes: dict):
        self.attributes = attributes

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _RecordingTracer:
    """Records the name and attributes of every span opened through it."""

    def __init__(self):
        self.spans: list[tuple[str, dict]] = []

    def start_as_current_span(self, name, attributes=None):
        recorded = dict(attributes or {})
        self.spans.append((name, recorded))
        return _RecordingSpan(recorded)


# Only identifiers, counts and mode flags may leave the process on a span. A
# recorded game state or an event payload on a span attribute is a data leak,
# because the collector is readable by anyone with access to it.
_PERMITTED_SPAN_ATTRIBUTES = {
    "game.id",
    "history.stream",
    "history.consumer_group",
    "history.events_processed",
    "history.reclaim_failed",
    "history.target_seq",
    "history.restore_mode",
    "history.ephemeral",
    "history.snapshot_at_seq",
    "history.platform",
}


async def test_snapshot_span_never_carries_the_snapshot_document(monkeypatch):
    """`take_snapshot` handles a full recorded game state; the span must not."""
    import history_service.runtime.snapshots as snapshots

    tracer = _RecordingTracer()
    monkeypatch.setattr(snapshots, "tracer", tracer)

    secret_state = {"cardById": {"c1": "a player's hand"}, "deltas": ["secret"]}

    class _GameService:
        async def get_snapshot(self, game_id):
            return secret_state

    class _Repository:
        async def write_snapshot(self, game_id, seq, document, platform="dragncards"):
            return SimpleNamespace(game_id=game_id, snapshot_at_seq=seq)

    service = snapshots.SnapshotService(
        settings=SimpleNamespace(
            snapshot_every_n_events=1, snapshot_max_interval_seconds=1
        ),
        repository=_Repository(),
        game_service=_GameService(),
    )

    await service.take_snapshot("game-1", 7)

    assert tracer.spans == [
        (
            "history.take_snapshot",
            {
                "game.id": "game-1",
                "history.platform": "dragncards",
                "history.snapshot_at_seq": 7,
            },
        )
    ]
    for _name, attributes in tracer.spans:
        assert set(attributes) <= _PERMITTED_SPAN_ATTRIBUTES
        assert "a player's hand" not in repr(attributes)


async def test_ingest_batch_span_records_counts_not_payloads(monkeypatch):
    import history_service.runtime.ingest as ingest

    tracer = _RecordingTracer()
    monkeypatch.setattr(ingest, "tracer", tracer)

    class _Client:
        async def execute(self, *parts):
            return None  # empty poll: no entries to handle

    ingester = ingest.StreamIngester(
        settings=Settings(),
        repository=MagicMock(),
        client=_Client(),
        snapshots=MagicMock(),
    )
    monkeypatch.setattr(ingester, "reclaim_pending", lambda: _noop())
    monkeypatch.setattr(ingester, "_check_lag", lambda: _noop())

    assert await ingester.process_batch() == 0

    name, attributes = tracer.spans[0]
    assert name == "history.ingest_batch"
    assert attributes["history.events_processed"] == 0
    assert set(attributes) <= _PERMITTED_SPAN_ATTRIBUTES


async def _noop():
    return 0
