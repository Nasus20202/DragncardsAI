"""The eval-service's telemetry must actually be wired, not merely available.

DRA-23: the service shipped with the OTEL_* environment variables set in
`docker-compose.yaml` but no instrumentation anywhere in its code, so nothing was
ever exported. These tests pin the code-level wiring, and — because this service
handles the judge prompt and the recorded game state it is built from — pin that
the workflow span carries identifiers and outcomes only.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dragncards_common import telemetry as shared_telemetry

import eval_service.telemetry as telemetry
from eval_service.runtime.app import create_app
from eval_service.storage.db import create_engine


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


def test_service_identity_defaults_to_eval_service(monkeypatch):
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)

    config = telemetry.TelemetryConfig.from_env(telemetry.DEFAULT_SERVICE_NAME)

    assert telemetry.DEFAULT_SERVICE_NAME == "eval-service"
    assert config.service_name == "eval-service"


def test_setup_telemetry_passes_the_service_name_to_the_shared_bootstrap(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(
        shared_telemetry,
        "setup_telemetry",
        lambda name: seen.append(name) or "runtime",
    )

    assert telemetry.setup_telemetry() == "runtime"
    assert seen == ["eval-service"]


def test_main_initializes_telemetry_before_serving(monkeypatch):
    """The bootstrap has to run in the entrypoint, not just be importable."""
    from eval_service import main as main_module

    calls: list[str] = []
    monkeypatch.setattr(
        main_module, "setup_telemetry", lambda: calls.append("setup_telemetry")
    )
    monkeypatch.setattr(
        main_module, "create_app", lambda settings: calls.append("create_app")
    )
    monkeypatch.setattr(
        main_module.uvicorn, "run", lambda app, host, port: calls.append("run")
    )

    main_module.main()

    assert calls == ["setup_telemetry", "create_app", "run"]


def test_create_app_instruments_the_server_edge(monkeypatch):
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
    instrumentor = MagicMock()
    monkeypatch.setattr(shared_telemetry, "_fastapi_instrumentor", lambda: instrumentor)
    monkeypatch.setattr(
        shared_telemetry, "setup_telemetry", lambda name: SimpleNamespace(enabled=True)
    )

    app = create_app(start_worker=False)

    instrumentor.instrument_app.assert_called_once_with(app)
    assert app.state._otel_instrumented is True


def test_create_app_skips_instrumentation_when_sdk_disabled(monkeypatch):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")

    app = create_app(start_worker=False)

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


# A span leaves the process and is readable by anyone with collector access, so
# the judge prompt, the recorded game state it is assembled from, and the judge's
# response are all forbidden. Only these keys may appear.
_PERMITTED_SPAN_ATTRIBUTES = {
    "eval.target_id",
    "eval.request_id",
    "eval.scope",
    "eval.target_seq",
    "eval.events_considered",
    "eval.outcome",
    "game.id",
}


@pytest.mark.asyncio
async def test_worker_emits_one_evaluate_target_span_per_graded_target(
    repository, monkeypatch
):
    from eval_service.config import Settings
    from eval_service.runtime.evaluator import Evaluator
    from eval_service.runtime.requests import RequestService
    from eval_service.runtime import worker as worker_module
    from eval_service.schemas.api import EvaluationRequestBody, Selection
    from tests.unit.conftest import (
        FakeHistoryClient,
        StubJudgeClient,
        agent_event,
        state_event,
    )

    tracer = _RecordingTracer()
    monkeypatch.setattr(worker_module, "tracer", tracer)

    settings = Settings(
        eval_judge_model="anthropic/claude-x",
        evaluator_version="eval-1",
        eval_max_attempts=1,
        eval_retry_backoff_seconds=0.0,
    )
    events = [
        state_event(game_id="g1", seq=1, round_number=1),
        agent_event(game_id="g1", seq=2, action="play"),
        state_event(game_id="g1", seq=3, round_number=1),
    ]
    history = FakeHistoryClient({"g1": events})
    judge = StubJudgeClient()
    evaluator = Evaluator(
        settings=settings, repository=repository, history=history, judge=judge
    )
    request_service = RequestService(
        settings=settings, repository=repository, history=history
    )
    worker = worker_module.EvaluationWorker(
        settings=settings,
        repository=repository,
        history=history,
        evaluator=evaluator,
    )
    resp = await request_service.create(
        "g1", EvaluationRequestBody(scope="move", selection=Selection(seqs=[2]))
    )

    await worker.drain_once()

    names = [name for name, _attributes in tracer.spans]
    assert names == ["eval.evaluate_target"]
    _name, attributes = tracer.spans[0]
    assert attributes["game.id"] == "g1"
    assert attributes["eval.scope"] == "move"
    assert attributes["eval.request_id"] == resp.request_id
    assert attributes["eval.outcome"] == "evaluated"
    assert set(attributes) <= _PERMITTED_SPAN_ATTRIBUTES


@pytest.mark.asyncio
async def test_evaluate_target_span_records_failure_as_an_outcome_not_a_message(
    repository, monkeypatch
):
    """A gateway error body can embed a prompt echo or a header; keep it off the span."""
    from eval_service.config import Settings
    from eval_service.integrations.bifrost import BifrostError
    from eval_service.runtime.evaluator import Evaluator
    from eval_service.runtime.requests import RequestService
    from eval_service.runtime import worker as worker_module
    from eval_service.schemas.api import EvaluationRequestBody, Selection
    from tests.unit.conftest import (
        FakeHistoryClient,
        StubJudgeClient,
        agent_event,
        state_event,
    )

    tracer = _RecordingTracer()
    monkeypatch.setattr(worker_module, "tracer", tracer)

    settings = Settings(
        eval_judge_model="anthropic/claude-x",
        evaluator_version="eval-1",
        eval_max_attempts=1,
        eval_retry_backoff_seconds=0.0,
    )
    events = [
        state_event(game_id="g1", seq=1, round_number=1),
        agent_event(game_id="g1", seq=2, action="play"),
        state_event(game_id="g1", seq=3, round_number=1),
    ]
    history = FakeHistoryClient({"g1": events})
    judge = StubJudgeClient(
        error=BifrostError(
            "gateway_error",
            "Authorization: Bearer secret-token, prompt was: the player's hand",
            retryable=False,
        )
    )
    evaluator = Evaluator(
        settings=settings, repository=repository, history=history, judge=judge
    )
    request_service = RequestService(
        settings=settings, repository=repository, history=history
    )
    worker = worker_module.EvaluationWorker(
        settings=settings,
        repository=repository,
        history=history,
        evaluator=evaluator,
    )
    await request_service.create(
        "g1", EvaluationRequestBody(scope="move", selection=Selection(seqs=[2]))
    )

    await worker.drain_once()

    _name, attributes = tracer.spans[0]
    assert set(attributes) <= _PERMITTED_SPAN_ATTRIBUTES
    rendered = repr(attributes)
    assert "secret-token" not in rendered
    assert "the player's hand" not in rendered
