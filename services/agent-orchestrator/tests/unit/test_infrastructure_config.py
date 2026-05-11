from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]


def _compose_default(value: str, expected_default: str) -> None:
    assert value.startswith("${")
    assert value.endswith("}")
    assert value.split(":-", 1)[1][:-1] == expected_default


def test_bifrost_config_includes_required_providers():
    config_path = ROOT / "services/bifrost/config.json"
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    plugin = payload["plugins"][0]
    providers = payload["providers"]
    assert plugin["name"] == "otel"
    assert plugin["config"]["service_name"] == "bifrost"
    assert plugin["config"]["collector_url"] == "http://otel-lgtm:4318/v1/traces"
    assert plugin["config"]["trace_type"] == "genai_extension"
    assert plugin["config"]["metrics_enabled"] is True
    assert plugin["config"]["metrics_endpoint"] == "http://otel-lgtm:4318/v1/metrics"
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
    game_service = payload["services"]["game-service"]
    service = payload["services"]["agent-orchestrator"]
    dashboard = payload["services"]["dashboard"]
    assert "otel-lgtm" in game_service["depends_on"]
    _compose_default(game_service["environment"]["OTEL_SERVICE_NAME"], "game-service")
    _compose_default(
        game_service["environment"]["OTEL_EXPORTER_OTLP_ENDPOINT"],
        "http://otel-lgtm:4318",
    )
    assert (
        service["build"]["dockerfile"]
        == "services/agent-orchestrator/docker/Dockerfile"
    )
    assert "agent-orchestrator-postgres" in service["depends_on"]
    assert "agent-orchestrator-valkey" in service["depends_on"]
    assert "bifrost" in service["depends_on"]
    assert "otel-lgtm" in service["depends_on"]
    assert service["env_file"] == [
        {"path": "services/agent-orchestrator/.env", "required": False}
    ]
    _compose_default(
        service["environment"]["VALKEY_URL"],
        "redis://agent-orchestrator-valkey:6379/0",
    )
    _compose_default(service["environment"]["OTEL_SERVICE_NAME"], "agent-orchestrator")
    _compose_default(dashboard["environment"]["OTEL_SERVICE_NAME"], "dashboard")
    assert "otel-lgtm" in dashboard["depends_on"]


def test_infra_compose_declares_bifrost_and_dedicated_postgres():
    compose_path = ROOT / "docker-compose.infra.yaml"
    payload = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = payload["services"]
    assert services["otel-lgtm"]["image"] == "grafana/otel-lgtm:0.27.1"
    assert services["otel-lgtm"]["volumes"] == [
        "./services/otel/loki-config.yaml:/otel-lgtm/loki-config.yaml:ro"
    ]
    assert services["otel-lgtm"]["ports"] == ["3004:3000", "4317:4317", "4318:4318"]
    assert services["otel-lgtm"]["healthcheck"]["test"] == [
        "CMD",
        "sh",
        "-lc",
        "test -f /tmp/ready",
    ]
    assert services["bifrost"]["image"] == "maximhq/bifrost:v1.5.0"
    assert services["bifrost"]["env_file"] == [
        {"path": "services/bifrost/.env", "required": False}
    ]
    assert services["bifrost"]["depends_on"] == {
        "otel-lgtm": {"condition": "service_healthy"}
    }
    assert (
        services["bifrost"]["environment"]["OTEL_RESOURCE_ATTRIBUTES"]
        == "deployment.environment=local,service.namespace=dragncardsai"
    )
    assert (
        services["agent-orchestrator-valkey"]["image"] == "valkey/valkey:9.0.4-alpine"
    )
    assert (
        services["agent-orchestrator-postgres"]["environment"]["POSTGRES_DB"]
        == "agent_orchestrator"
    )
