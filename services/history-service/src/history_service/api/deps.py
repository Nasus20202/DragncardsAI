from __future__ import annotations

from fastapi import Request

from history_service.config import Settings
from history_service.integrations.game_service import GameServiceClient
from history_service.integrations.orchestrator import OrchestratorClient
from history_service.runtime.restore import RestoreService
from history_service.runtime.snapshots import SnapshotService
from history_service.storage.repository import Repository


def get_repository(request: Request) -> Repository:
    return request.app.state.repository


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_snapshot_service(request: Request) -> SnapshotService:
    return request.app.state.snapshot_service


def get_restore_service(request: Request) -> RestoreService:
    return request.app.state.restore_service


def get_game_service_client(request: Request) -> GameServiceClient:
    return request.app.state.game_service_client


def get_orchestrator_client(request: Request) -> OrchestratorClient:
    return request.app.state.orchestrator_client
