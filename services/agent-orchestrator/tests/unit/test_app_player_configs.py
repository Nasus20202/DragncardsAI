from __future__ import annotations

from fastapi.testclient import TestClient


def _create_session(client: TestClient) -> str:
    return client.post("/sessions", json={"name": "orchestrator"}).json()["session"][
        "id"
    ]


def test_two_seats_are_configured_independently(app):
    provider_id = app.state.settings.enabled_provider_ids[0]
    with TestClient(app) as client:
        session_id = _create_session(client)

        first = client.put(
            f"/sessions/{session_id}/players/player1",
            json={
                "display_name": "Spider-Man",
                "provider_id": provider_id,
                "model_name": "model-a",
                "reasoning": {"enabled": True, "effort": "high"},
                "skills": ["demo-skill"],
            },
        )
        assert first.status_code == 200

        second = client.put(
            f"/sessions/{session_id}/players/player2",
            json={"model_name": "model-b", "reasoning": {"enabled": False}},
        )
        assert second.status_code == 200

        listed = client.get(f"/sessions/{session_id}/players")
        assert listed.status_code == 200
        players = listed.json()["players"]
        assert [p["player_id"] for p in players] == ["player1", "player2"]

        player1, player2 = players
        assert player1["display_name"] == "Spider-Man"
        assert player1["model_name"] == "model-a"
        assert player1["reasoning"] == {"effort": "high"}
        assert player1["skills"] == ["demo-skill"]

        # The second seat differs on exactly the axes it set; everything else
        # stays unset so it inherits the session.
        assert player2["model_name"] == "model-b"
        assert player2["provider_id"] is None
        assert player2["reasoning"] is None
        assert player2["skills"] is None


def test_roster_is_returned_on_the_session_detail(app):
    with TestClient(app) as client:
        session_id = _create_session(client)
        client.put(f"/sessions/{session_id}/players/player1", json={})

        detail = client.get(f"/sessions/{session_id}").json()["session"]

        assert [p["player_id"] for p in detail["players"]] == ["player1"]


def test_writing_a_seat_twice_updates_it_in_place(app):
    with TestClient(app) as client:
        session_id = _create_session(client)
        client.put(
            f"/sessions/{session_id}/players/player1", json={"model_name": "first"}
        )
        client.put(
            f"/sessions/{session_id}/players/player1", json={"model_name": "second"}
        )

        players = client.get(f"/sessions/{session_id}/players").json()["players"]

        assert len(players) == 1
        assert players[0]["model_name"] == "second"


def test_seat_can_be_deleted(app):
    with TestClient(app) as client:
        session_id = _create_session(client)
        client.put(f"/sessions/{session_id}/players/player1", json={})

        assert (
            client.delete(f"/sessions/{session_id}/players/player1").status_code == 204
        )
        assert client.get(f"/sessions/{session_id}/players").json()["players"] == []
        assert (
            client.delete(f"/sessions/{session_id}/players/player1").status_code == 404
        )


def test_invalid_seat_id_is_rejected(app):
    with TestClient(app) as client:
        session_id = _create_session(client)

        response = client.put(f"/sessions/{session_id}/players/player9", json={})

        assert response.status_code == 400
        assert "player1" in response.json()["detail"]


def test_unsupported_provider_is_rejected(app):
    with TestClient(app) as client:
        session_id = _create_session(client)

        response = client.put(
            f"/sessions/{session_id}/players/player1",
            json={"provider_id": "not-a-provider"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Unsupported provider"


def test_unknown_skill_is_rejected(app):
    with TestClient(app) as client:
        session_id = _create_session(client)

        response = client.put(
            f"/sessions/{session_id}/players/player1",
            json={"skills": ["demo-skill", "no-such-skill"]},
        )

        assert response.status_code == 400
        assert "no-such-skill" in response.json()["detail"]


def test_too_many_skills_is_rejected(app):
    with TestClient(app) as client:
        session_id = _create_session(client)

        response = client.put(
            f"/sessions/{session_id}/players/player1",
            json={"skills": [f"skill-{n}" for n in range(40)]},
        )

        assert response.status_code == 422


def test_seat_skills_are_registered_so_a_player_agent_can_enable_them(app):
    # A seat may name a skill no session has ever enabled. Enabling it on the
    # child at spawn time needs a registry row, so writing the seat must create
    # one or the skill would be silently dropped.
    with TestClient(app) as client:
        session_id = _create_session(client)

        # Enabling a skill only succeeds once it has a global registry row, so
        # this PATCH is a direct probe for one. Any skill present in the skill
        # roots has a row, because startup syncs them.
        before = client.patch(
            f"/sessions/{session_id}/skills/demo-skill", json={"enabled": True}
        )
        assert before.status_code == 200

        client.put(
            f"/sessions/{session_id}/players/player1", json={"skills": ["demo-skill"]}
        )

        after = client.patch(
            f"/sessions/{session_id}/skills/demo-skill", json={"enabled": True}
        )
        assert after.status_code == 200


def test_unknown_session_is_rejected(app):
    with TestClient(app) as client:
        assert client.get("/sessions/missing/players").status_code == 404
        assert (
            client.put("/sessions/missing/players/player1", json={}).status_code == 404
        )
