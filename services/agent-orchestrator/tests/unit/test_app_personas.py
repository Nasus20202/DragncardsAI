"""Persona CRUD, validation, and the session's default subagent persona."""

from __future__ import annotations

from fastapi.testclient import TestClient

from agent_orchestrator.runtime.personas import MAX_PERSONA_PROMPT_CHARS

RULES_LAWYER = {
    "display_name": "Rules Lawyer",
    "description": "Checks rule interactions against the printed rules.",
    "system_prompt": "Answer only from the printed rules. Cite the rule you used.",
    "skills": ["demo-skill"],
    "allowed_tools": ["game_service_next_step"],
}


def test_persona_is_created_and_read_back(app):
    with TestClient(app) as client:
        written = client.put("/personas/rules-lawyer", json=RULES_LAWYER)
        assert written.status_code == 200

        persona = client.get("/personas/rules-lawyer").json()["persona"]

        assert persona["name"] == "rules-lawyer"
        assert persona["display_name"] == "Rules Lawyer"
        assert persona["system_prompt"] == RULES_LAWYER["system_prompt"]
        assert persona["skills"] == ["demo-skill"]
        assert persona["allowed_tools"] == ["game_service_next_step"]
        # Unset provider/model mean "inherit the spawning session".
        assert persona["provider_id"] is None
        assert persona["model_name"] is None


def test_personas_are_listed_in_name_order(app):
    with TestClient(app) as client:
        client.put("/personas/rules-lawyer", json=RULES_LAWYER)
        client.put("/personas/deck-builder", json={"system_prompt": "Build decks."})

        listed = client.get("/personas").json()["personas"]

        assert [item["name"] for item in listed] == ["deck-builder", "rules-lawyer"]


def test_writing_a_persona_twice_replaces_it(app):
    with TestClient(app) as client:
        client.put("/personas/rules-lawyer", json={"system_prompt": "first"})
        second = client.put(
            "/personas/rules-lawyer",
            json={"system_prompt": "second", "allowed_tools": []},
        )

        assert second.status_code == 200
        persona = client.get("/personas/rules-lawyer").json()["persona"]
        assert persona["system_prompt"] == "second"
        # An empty allowlist is a real value — the persona gets no MCP tools.
        assert persona["allowed_tools"] == []


def test_reasoning_is_folded_into_gateway_options(app):
    with TestClient(app) as client:
        client.put(
            "/personas/careful",
            json={
                "system_prompt": "Think it through.",
                "reasoning": {"enabled": True, "effort": "high", "max_tokens": 2048},
            },
        )

        persona = client.get("/personas/careful").json()["persona"]

        assert persona["reasoning"] == {"effort": "high", "max_tokens": 2048}
        assert persona["gateway_options"]["reasoning"] == {
            "effort": "high",
            "max_tokens": 2048,
        }


def test_reasoning_disabled_removes_it_entirely(app):
    with TestClient(app) as client:
        client.put(
            "/personas/blunt",
            json={"system_prompt": "Answer.", "reasoning": {"enabled": False}},
        )

        persona = client.get("/personas/blunt").json()["persona"]

        assert persona["reasoning"] is None
        assert "reasoning" not in persona["gateway_options"]


def test_persona_is_deletable_and_deleting_twice_is_not_found(app):
    with TestClient(app) as client:
        client.put("/personas/rules-lawyer", json=RULES_LAWYER)

        assert client.delete("/personas/rules-lawyer").status_code == 204
        assert client.delete("/personas/rules-lawyer").status_code == 404
        assert client.get("/personas/rules-lawyer").status_code == 404
        assert client.get("/personas").json()["personas"] == []


def test_unknown_persona_is_not_found(app):
    with TestClient(app) as client:
        assert client.get("/personas/never-written").status_code == 404


# --- Validation ---------------------------------------------------------------


def test_a_name_that_is_not_a_slug_is_rejected(app):
    with TestClient(app) as client:
        rejected = client.put("/personas/Rules Lawyer", json={"system_prompt": "x"})

        assert rejected.status_code == 400
        assert "slug" in rejected.json()["detail"]
        assert client.get("/personas").json()["personas"] == []


def test_an_oversized_prompt_is_rejected(app):
    with TestClient(app) as client:
        rejected = client.put(
            "/personas/verbose",
            json={"system_prompt": "x" * (MAX_PERSONA_PROMPT_CHARS + 1)},
        )

        assert rejected.status_code == 422
        assert client.get("/personas").json()["personas"] == []


def test_a_prompt_at_the_limit_is_accepted(app):
    with TestClient(app) as client:
        written = client.put(
            "/personas/verbose",
            json={"system_prompt": "x" * MAX_PERSONA_PROMPT_CHARS},
        )

        assert written.status_code == 200


def test_an_unsupported_provider_is_rejected(app):
    with TestClient(app) as client:
        rejected = client.put(
            "/personas/exotic",
            json={"system_prompt": "x", "provider_id": "not-enabled"},
        )

        assert rejected.status_code == 400
        assert rejected.json()["detail"] == "Unsupported provider"
        assert client.get("/personas").json()["personas"] == []


def test_an_unknown_skill_is_rejected_and_named(app):
    with TestClient(app) as client:
        rejected = client.put(
            "/personas/rules-lawyer",
            json={"system_prompt": "x", "skills": ["demo-skill", "no-such-skill"]},
        )

        assert rejected.status_code == 400
        assert rejected.json()["detail"] == "Unknown skill: no-such-skill"
        assert client.get("/personas").json()["personas"] == []


def test_a_persona_carries_no_credential_fields(app):
    """A persona NAMES a provider configuration and never holds a key."""
    with TestClient(app) as client:
        client.put("/personas/plain", json={"system_prompt": "x"})
        persona = client.get("/personas/plain").json()["persona"]

        assert "api_key" not in persona
        assert not any("key" in field for field in persona)


# --- Session default subagent persona -----------------------------------------


def test_session_records_a_default_subagent_persona(app):
    with TestClient(app) as client:
        client.put("/personas/rules-lawyer", json=RULES_LAWYER)

        created = client.post(
            "/sessions",
            json={"name": "s", "default_subagent_persona": "rules-lawyer"},
        )

        assert created.status_code == 201
        assert created.json()["session"]["default_subagent_persona"] == "rules-lawyer"

        session_id = created.json()["session"]["id"]
        fetched = client.get(f"/sessions/{session_id}").json()["session"]
        assert fetched["default_subagent_persona"] == "rules-lawyer"


def test_session_default_persona_can_be_set_and_cleared(app):
    with TestClient(app) as client:
        client.put("/personas/rules-lawyer", json=RULES_LAWYER)
        session_id = client.post("/sessions", json={"name": "s"}).json()["session"][
            "id"
        ]

        updated = client.patch(
            f"/sessions/{session_id}",
            json={"default_subagent_persona": "rules-lawyer"},
        )
        assert updated.json()["session"]["default_subagent_persona"] == "rules-lawyer"

        cleared = client.patch(
            f"/sessions/{session_id}", json={"default_subagent_persona": None}
        )
        assert cleared.json()["session"]["default_subagent_persona"] is None


def test_an_unknown_default_persona_is_rejected(app):
    with TestClient(app) as client:
        rejected = client.post(
            "/sessions", json={"name": "s", "default_subagent_persona": "nope"}
        )

        assert rejected.status_code == 400
        assert rejected.json()["detail"] == "Unknown persona: nope"

        session_id = client.post("/sessions", json={"name": "s"}).json()["session"][
            "id"
        ]
        patched = client.patch(
            f"/sessions/{session_id}", json={"default_subagent_persona": "nope"}
        )
        assert patched.status_code == 400


def test_deleting_a_persona_clears_it_as_a_session_default(app):
    with TestClient(app) as client:
        client.put("/personas/rules-lawyer", json=RULES_LAWYER)
        session_id = client.post(
            "/sessions",
            json={"name": "s", "default_subagent_persona": "rules-lawyer"},
        ).json()["session"]["id"]

        assert client.delete("/personas/rules-lawyer").status_code == 204

        session = client.get(f"/sessions/{session_id}").json()["session"]
        assert session["default_subagent_persona"] is None


def test_a_session_without_a_default_reports_none(app):
    with TestClient(app) as client:
        session = client.post("/sessions", json={"name": "s"}).json()["session"]

        assert session["default_subagent_persona"] is None
