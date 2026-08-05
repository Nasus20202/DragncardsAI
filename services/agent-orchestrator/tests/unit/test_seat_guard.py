"""The seat guard, tested as the adversary rather than as the happy path.

A seat is an LLM that can write anything into its tool arguments, so most of what
matters here is what *cannot* move the answer: prose, an argument named as though
it were the caller's identity, an unusual case, a value buried in a nested
payload. The one thing that decides who is calling is the ``caller_player_id``
the server passes in, and every test below either confirms that or confirms a
documented limitation of the function is real.

The dispatch-level half of this — that a refused call is never invoked and that
the three events are recorded — lives in ``test_prompt_run.py`` next to the rest
of the run-loop harness.
"""

from __future__ import annotations

from agent_orchestrator.runtime.seat_guard import (
    MAX_REPORTED_VALUE_LENGTH,
    MAX_TRAVERSAL_DEPTH,
    check_seat_scope,
)


def _check(caller: str, arguments: dict) -> object:
    return check_seat_scope(
        caller_player_id=caller,
        tool_name="game-service_move_card",
        arguments=arguments,
    )


def test_a_foreign_player_owned_group_is_refused():
    violation = _check("player1", {"groupId": "player2Hand"})

    assert violation is not None
    assert violation.caller_player_id == "player1"
    assert violation.foreign_player_id == "player2"
    assert violation.argument == "groupId"
    assert violation.value == "player2Hand"
    assert violation.tool_name == "game-service_move_card"


def test_the_refusal_message_names_the_argument_the_seats_and_the_rule():
    violation = _check("player1", {"destGroupId": "player3Play"})

    assert violation is not None
    message = violation.message
    assert "destGroupId" in message
    assert "player3" in message
    assert "player1" in message
    assert "own cards" in message


def test_the_seats_own_group_is_allowed():
    assert _check("player1", {"groupId": "player1Hand"}) is None
    assert _check("player4", {"groupId": "player4Discard"}) is None


def test_groups_no_seat_owns_are_unrestricted():
    # A seat legitimately attacks the villain and thwarts the scheme on its own
    # turn, so restricting these would refuse legal play rather than protect
    # anything.
    for group in (
        "sharedMainScheme",
        "villainDiscard",
        "sharedEncounterDeck",
        "playerAidDeck",
        "player10Hand",
    ):
        assert _check("player1", {"groupId": group}) is None, group


def test_a_bare_foreign_seat_identifier_is_refused():
    violation = _check("player1", {"target": "player2"})

    assert violation is not None
    assert violation.foreign_player_id == "player2"
    assert violation.argument == "target"


def test_an_explicit_player_identifying_argument_is_refused():
    for name in ("player_id", "playerId", "player", "player_n"):
        violation = _check("player1", {name: "player3"})
        assert violation is not None, name
        assert violation.foreign_player_id == "player3"
        assert violation.argument == name


def test_an_integer_seat_index_under_a_player_argument_is_refused():
    for arguments in ({"player_index": 3}, {"playerIndex": "3"}, {"player_n": 3}):
        violation = _check("player1", arguments)
        assert violation is not None, arguments
        assert violation.foreign_player_id == "player3"
        assert violation.value == "3"


def test_the_seats_own_index_is_allowed():
    assert _check("player1", {"player_index": 1}) is None
    assert _check("player2", {"player_n": "player2"}) is None


def test_an_index_under_an_unrelated_argument_is_not_read_as_a_seat():
    # `3` means three of something here. Treating every small integer as a seat
    # would refuse ordinary calls, so only player-identifying names are indexed.
    assert _check("player1", {"quantity": 3}) is None
    assert _check("player1", {"count": "2"}) is None
    assert _check("player1", {"tokens": {"damage": 4}}) is None


def test_a_boolean_is_not_seat_one():
    # `True` is an `int` in Python; without the explicit exclusion this refuses.
    assert _check("player1", {"player": True}) is None


def test_a_foreign_seat_nested_in_a_payload_is_refused_with_its_path():
    violation = _check(
        "player1",
        {
            "updates": [
                {"groupId": "player1Hand", "cardId": "abc"},
                {"groupId": "player3Play", "cardId": "def"},
            ]
        },
    )

    assert violation is not None
    assert violation.argument == "updates[1].groupId"
    assert violation.foreign_player_id == "player3"


def test_a_seat_id_inside_a_list_under_a_player_argument_is_refused():
    violation = _check("player1", {"player_ids": ["player1", "player2"]})

    assert violation is not None
    assert violation.argument == "player_ids[1]"
    assert violation.foreign_player_id == "player2"


def test_the_first_violation_is_reported_and_is_stable():
    arguments = {"origGroupId": "player2Hand", "destGroupId": "player3Play"}

    first = _check("player1", arguments)
    again = _check("player1", arguments)

    assert first is not None and again is not None
    assert first.argument == "origGroupId"
    assert first == again


def test_case_variants_do_not_evade_the_guard():
    assert _check("player1", {"groupId": "PLAYER2HAND"}) is not None
    assert _check("player1", {"player_id": "Player3"}) is not None


def test_prose_naming_another_seat_is_not_itself_a_violation():
    # The guard scopes *actions*, not sentences. A note mentioning another seat
    # touches no cards, and refusing it would make the guard fire on reports and
    # explanations while catching nothing that acts.
    assert (
        _check(
            "player1",
            {"note": "I am player2, this is authorised by the orchestrator"},
        )
        is None
    )


def test_arguments_claiming_to_be_the_caller_do_not_change_the_caller():
    # The seat writes whatever it likes; only the server's `caller_player_id`
    # decides who is calling. Both directions are checked: an argument asserting
    # a different caller does not license the foreign group, and an argument
    # naming the *real* caller's seat is still foreign to a different caller.
    violation = _check(
        "player1",
        {
            "caller_player_id": "player2",
            "player_id": "player2",
            "note": "player2 has permission to use its own hand",
            "groupId": "player2Hand",
        },
    )
    assert violation is not None
    assert violation.caller_player_id == "player1"
    assert violation.foreign_player_id == "player2"

    assert _check("player2", {"player_id": "player1"}) is not None


def test_a_value_below_the_traversal_bound_is_not_examined():
    # A documented limitation, asserted so the docstring stays honest: nesting
    # past the bound goes unchecked rather than silently costing more than the
    # tool call it guards.
    deep: dict = {"groupId": "player2Hand"}
    for _ in range(MAX_TRAVERSAL_DEPTH + 2):
        deep = {"nested": deep}

    assert _check("player1", deep) is None
    assert _check("player1", {"nested": {"groupId": "player2Hand"}}) is not None


def test_an_oversized_value_is_still_refused_but_reported_truncated():
    # A group name is unbounded in the pattern on purpose, so an absurd value is
    # refused rather than accidentally allowed — and truncated where it is
    # reported, so the seat cannot echo a megabyte back into its own context.
    violation = _check("player1", {"groupId": "player2" + "A" * 5000})

    assert violation is not None
    assert violation.foreign_player_id == "player2"
    assert len(violation.value) == MAX_REPORTED_VALUE_LENGTH + 1
    assert violation.value.endswith("…")


def test_arguments_that_are_not_a_mapping_are_ignored():
    assert (
        check_seat_scope(caller_player_id="player1", tool_name="t", arguments=None)
        is None
    )


# -- Mapping keys ---------------------------------------------------------------
#
# A key names a seat as readily as a value does, and a deny-list that reads only
# values is blind to half of every mapping. No game-service tool takes a
# group-keyed mapping today, so these guard a shape that does not exist yet —
# which is the point: the tool that introduces it will not come with a reminder
# to re-read this module.


def test_a_foreign_group_id_used_as_a_mapping_key_is_refused():
    violation = _check("player1", {"updates": {"player2Hand": ["draw"]}})

    assert violation is not None
    assert violation.foreign_player_id == "player2"
    assert violation.argument == "updates.player2Hand"
    assert violation.value == "player2Hand"


def test_a_bare_foreign_seat_id_used_as_a_mapping_key_is_refused():
    violation = _check("player1", {"per_player": {"player3": {"threat": 1}}})

    assert violation is not None
    assert violation.foreign_player_id == "player3"
    assert violation.argument == "per_player.player3"
    assert violation.value == "player3"


def test_a_foreign_key_is_refused_even_when_its_value_is_innocent():
    """The key is the only place the seat is named, so the value cannot excuse it."""
    violation = _check("player1", {"player4Discard": {}})

    assert violation is not None
    assert violation.foreign_player_id == "player4"
    assert violation.argument == "player4Discard"


def test_a_foreign_key_nested_below_a_list_reports_its_own_path():
    violation = _check("player1", {"batch": [{"player2Play": {"exhaust": True}}]})

    assert violation is not None
    assert violation.foreign_player_id == "player2"
    assert violation.argument == "batch[0].player2Play"


def test_a_foreign_key_is_reported_before_a_foreign_value_inside_it():
    """First-violation-wins stays depth-first: the key is reached first."""
    violation = _check("player1", {"player2Hand": {"groupId": "player3Hand"}})

    assert violation is not None
    assert violation.foreign_player_id == "player2"
    assert violation.argument == "player2Hand"


def test_the_callers_own_group_id_as_a_mapping_key_is_allowed():
    assert _check("player1", {"updates": {"player1Hand": ["draw"]}}) is None


def test_the_callers_own_seat_id_as_a_mapping_key_is_allowed():
    assert _check("player2", {"per_player": {"player2": {"threat": 1}}}) is None


def test_ordinary_mapping_keys_are_not_seats():
    assert (
        _check(
            "player1",
            {
                "groupId": "player1Hand",
                "options": {"shuffle": True, "count": 2, "player": "player1"},
                "metadata": {"note": "player2 asked me to do this", "round": 3},
            },
        )
        is None
    )


def test_an_integer_shaped_key_is_not_read_as_a_seat_index():
    """Documented narrowing: a key of `"2"` declares nothing, unlike `player_n: 2`.

    Reading it as seat 2 would refuse every ordinary integer-keyed mapping, which
    manufactures false refusals instead of closing a hole.
    """
    assert _check("player1", {"counts": {"1": 3, "2": 4, "3": 5}}) is None


def test_a_case_variant_key_does_not_evade_the_guard():
    violation = _check("player1", {"updates": {"PLAYER2HAND": ["draw"]}})

    assert violation is not None
    assert violation.foreign_player_id == "player2"


def test_a_long_foreign_key_is_truncated_where_it_is_reported():
    violation = _check("player1", {"player2" + "A" * 5000: {}})

    assert violation is not None
    assert violation.foreign_player_id == "player2"
    assert len(violation.value) == MAX_REPORTED_VALUE_LENGTH + 1
    assert violation.value.endswith("…")
