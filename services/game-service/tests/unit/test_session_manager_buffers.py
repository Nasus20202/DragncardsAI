from __future__ import annotations

from .session_manager_test_support import fire_event, make_session


def test_alert_appended_on_send_alert_event():
    session = make_session()
    fire_event(session.channel, "send_alert", {"level": "info", "text": "hello"})
    assert len(session.get_alerts()) == 1
    assert session.get_alerts()[0]["text"] == "hello"


def test_alert_buffer_multiple_alerts():
    session = make_session()
    for index in range(5):
        fire_event(session.channel, "send_alert", {"level": "info", "text": str(index)})
    alerts = session.get_alerts()
    assert len(alerts) == 5
    assert [alert["text"] for alert in alerts] == ["0", "1", "2", "3", "4"]


def test_alert_buffer_evicts_at_maxlen_50():
    session = make_session()
    for index in range(55):
        fire_event(session.channel, "send_alert", {"text": str(index)})
    alerts = session.get_alerts()
    assert len(alerts) == 50
    assert alerts[0]["text"] == "5"
    assert alerts[-1]["text"] == "54"


def test_get_alerts_returns_copy():
    session = make_session()
    fire_event(session.channel, "send_alert", {"text": "x"})
    alerts = session.get_alerts()
    alerts.clear()
    assert len(session.get_alerts()) == 1


def test_gui_update_stored_by_player_n():
    session = make_session()
    fire_event(
        session.channel,
        "gui_update",
        {"player_n": "player1", "prompt": "choose target"},
    )
    updates = session.get_gui_updates()
    assert "player1" in updates
    assert updates["player1"]["prompt"] == "choose target"


def test_gui_update_overwrites_previous_for_same_player():
    session = make_session()
    fire_event(
        session.channel, "gui_update", {"player_n": "player1", "prompt": "first"}
    )
    fire_event(
        session.channel, "gui_update", {"player_n": "player1", "prompt": "second"}
    )
    assert session.get_gui_updates()["player1"]["prompt"] == "second"


def test_gui_update_different_players_stored_separately():
    session = make_session()
    fire_event(session.channel, "gui_update", {"player_n": "player1", "prompt": "p1"})
    fire_event(session.channel, "gui_update", {"player_n": "player2", "prompt": "p2"})
    updates = session.get_gui_updates()
    assert updates["player1"]["prompt"] == "p1"
    assert updates["player2"]["prompt"] == "p2"


def test_gui_update_payload_without_player_n_ignored():
    session = make_session()
    fire_event(session.channel, "gui_update", {"no_player_field": True})
    assert session.get_gui_updates() == {}


def test_get_gui_updates_returns_copy():
    session = make_session()
    fire_event(session.channel, "gui_update", {"player_n": "player1", "prompt": "x"})
    updates = session.get_gui_updates()
    updates.clear()
    assert "player1" in session.get_gui_updates()
