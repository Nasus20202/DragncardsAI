from __future__ import annotations

from types import SimpleNamespace

from agent_orchestrator.runtime.player_agents import (
    fold_reasoning,
    is_valid_player_id,
    resolve_player_agent_config,
    resolve_roster,
    session_player_id,
    unfold_reasoning,
)


def make_parent(
    *,
    provider_id="openai",
    model_name="gpt-4o-mini",
    gateway_options=None,
    provider_options=None,
    skills=("rules",),
    metadata=None,
):
    return SimpleNamespace(
        id="parent",
        metadata_json=metadata or {},
        model_config=SimpleNamespace(
            provider_id=provider_id,
            model_name=model_name,
            gateway_options=gateway_options or {},
            provider_options=provider_options or {},
        ),
        enabled_skills=[
            SimpleNamespace(skill_name=name, enabled=True) for name in skills
        ],
    )


def make_config(
    player_id="player1",
    *,
    display_name=None,
    provider_id=None,
    model_name=None,
    gateway_options=None,
    provider_options=None,
    skills_json=None,
):
    return SimpleNamespace(
        player_id=player_id,
        display_name=display_name,
        provider_id=provider_id,
        model_name=model_name,
        gateway_options=gateway_options or {},
        provider_options=provider_options or {},
        skills_json=skills_json,
    )


def test_valid_player_ids_are_the_four_marvel_champions_seats():
    assert all(is_valid_player_id(f"player{n}") for n in (1, 2, 3, 4))
    assert not is_valid_player_id("player0")
    assert not is_valid_player_id("player5")
    assert not is_valid_player_id("villain")
    assert not is_valid_player_id("Player1")


def test_unset_fields_inherit_from_the_orchestrator_session():
    parent = make_parent(
        gateway_options={"temperature": 0.2}, provider_options={"top_k": 3}
    )

    resolved = resolve_player_agent_config(parent, make_config())

    assert resolved.provider_id == "openai"
    assert resolved.model_name == "gpt-4o-mini"
    assert resolved.gateway_options == {"temperature": 0.2}
    assert resolved.provider_options == {"top_k": 3}
    assert resolved.skills == ["rules"]


def test_set_fields_override_the_session():
    parent = make_parent()

    resolved = resolve_player_agent_config(
        parent,
        make_config(provider_id="gemini", model_name="gemini-2.0-flash"),
    )

    assert resolved.provider_id == "gemini"
    assert resolved.model_name == "gemini-2.0-flash"


def test_options_are_overlaid_not_replaced():
    parent = make_parent(gateway_options={"temperature": 0.2, "top_p": 0.9})

    resolved = resolve_player_agent_config(
        parent, make_config(gateway_options={"temperature": 0.9})
    )

    # The seat changed one knob; the rest of the session's options survive.
    assert resolved.gateway_options == {"temperature": 0.9, "top_p": 0.9}


def test_skills_list_overrides_and_empty_list_means_no_skills():
    parent = make_parent(skills=("rules", "learn-to-play"))

    overridden = resolve_player_agent_config(
        parent, make_config(skills_json=["learn-to-play"])
    )
    assert overridden.skills == ["learn-to-play"]

    emptied = resolve_player_agent_config(parent, make_config(skills_json=[]))
    assert emptied.skills == []


def test_disabled_parent_skills_are_not_inherited():
    parent = make_parent()
    parent.enabled_skills.append(SimpleNamespace(skill_name="off", enabled=False))

    resolved = resolve_player_agent_config(parent, make_config())

    assert resolved.skills == ["rules"]


def test_parent_without_model_config_resolves_to_none():
    parent = SimpleNamespace(metadata_json={}, model_config=None, enabled_skills=[])

    resolved = resolve_player_agent_config(parent, make_config())

    assert resolved.provider_id is None
    assert resolved.model_name is None
    assert resolved.gateway_options == {}


def test_fold_reasoning_writes_the_key_the_runtime_reads():
    folded = fold_reasoning({}, enabled=True, effort="high", max_tokens=2048)

    assert folded == {"reasoning": {"effort": "high", "max_tokens": 2048}}
    assert unfold_reasoning(folded) == {"effort": "high", "max_tokens": 2048}


def test_fold_reasoning_disabled_removes_the_key_entirely():
    folded = fold_reasoning(
        {"reasoning": {"effort": "low"}, "temperature": 0.1},
        enabled=False,
        effort="high",
        max_tokens=10,
    )

    assert folded == {"temperature": 0.1}
    assert unfold_reasoning(folded) is None


def test_fold_reasoning_with_no_values_removes_the_key():
    folded = fold_reasoning(
        {"reasoning": {"effort": "low"}}, enabled=True, effort=None, max_tokens=None
    )

    assert folded == {}


def test_resolved_summary_reports_reasoning_and_skills():
    parent = make_parent(gateway_options={"reasoning": {"effort": "medium"}})

    resolved = resolve_player_agent_config(
        parent, make_config(display_name="Spider-Man")
    )

    assert resolved.as_summary() == {
        "player_id": "player1",
        "display_name": "Spider-Man",
        "provider_id": "openai",
        "model_name": "gpt-4o-mini",
        "reasoning": {"effort": "medium"},
        "skills": ["rules"],
    }


def test_roster_is_ordered_by_seat():
    parent = make_parent()

    roster = resolve_roster(parent, [make_config("player2"), make_config("player1")])

    assert [entry.player_id for entry in roster] == ["player1", "player2"]


def test_session_player_id_reads_metadata_and_rejects_junk():
    assert session_player_id(
        SimpleNamespace(metadata_json={"player_id": "player2"})
    ) == ("player2")
    assert session_player_id(SimpleNamespace(metadata_json={})) is None
    assert (
        session_player_id(SimpleNamespace(metadata_json={"player_id": "nope"})) is None
    )
    assert session_player_id(SimpleNamespace(metadata_json=None)) is None
