from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[4]


def test_bifrost_config_includes_required_providers():
    config_path = ROOT / "services/bifrost/config.json"
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    providers = payload["providers"]
    assert "openai" in providers
    assert "anthropic" in providers
    assert "gemini" in providers
    assert "mistral" in providers
    assert "openrouter" in providers
    assert "nvidia" in providers
    assert "lmstudio" in providers


def test_root_compose_declares_agent_orchestrator():
    compose_path = ROOT / "docker-compose.yaml"
    payload = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    service = payload["services"]["agent-orchestrator"]
    assert service["build"]["dockerfile"] == "services/agent-orchestrator/docker/Dockerfile"
    assert "agent-orchestrator-postgres" in service["depends_on"]
    assert "agent-orchestrator-valkey" in service["depends_on"]
    assert "bifrost" in service["depends_on"]
    assert service["env_file"] == [{"path": "services/agent-orchestrator/.env", "required": False}]
    assert service["environment"]["VALKEY_URL"] == "redis://agent-orchestrator-valkey:6379/0"


def test_infra_compose_declares_bifrost_and_dedicated_postgres():
    compose_path = ROOT / "docker-compose.infra.yaml"
    payload = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = payload["services"]
    assert services["bifrost"]["image"] == "maximhq/bifrost:v1.5.0"
    assert services["bifrost"]["env_file"] == [{"path": "services/bifrost/.env", "required": False}]
    assert services["agent-orchestrator-valkey"]["image"] == "valkey/valkey:9.0.4-alpine"
    assert services["agent-orchestrator-postgres"]["environment"]["POSTGRES_DB"] == "agent_orchestrator"
