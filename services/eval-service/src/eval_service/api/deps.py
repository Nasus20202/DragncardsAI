from __future__ import annotations

from fastapi import Request

from eval_service.config import Settings
from eval_service.integrations.bifrost import BifrostJudgeClient
from eval_service.integrations.history import HistoryClient
from eval_service.runtime.inflight import InflightRegistry
from eval_service.runtime.live_events import LiveEventBus
from eval_service.runtime.requests import RequestService
from eval_service.runtime.rounds import RoundsService
from eval_service.runtime.stream import EvaluationStreamService
from eval_service.runtime.worker import EvaluationWorker
from eval_service.storage.repository import Repository


def get_repository(request: Request) -> Repository:
    return request.app.state.repository


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_history_client(request: Request) -> HistoryClient:
    return request.app.state.history_client


def get_judge_client(request: Request) -> BifrostJudgeClient:
    return request.app.state.judge_client


def get_request_service(request: Request) -> RequestService:
    return request.app.state.request_service


def get_rounds_service(request: Request) -> RoundsService:
    return request.app.state.rounds_service


def get_worker(request: Request) -> EvaluationWorker | None:
    return getattr(request.app.state, "worker", None)


def get_live_bus(request: Request) -> LiveEventBus:
    return request.app.state.live_bus


def get_inflight(request: Request) -> InflightRegistry:
    return request.app.state.inflight


def get_stream_service(request: Request) -> EvaluationStreamService:
    return request.app.state.stream_service
