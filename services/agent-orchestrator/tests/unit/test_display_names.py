from __future__ import annotations

from agent_orchestrator.runtime.display_names import (
    MAX_GENERATED_NAME_CHARS,
    generate_agent_name,
)

# The boilerplate opening that made every truncated subagent name identical.
BOILERPLATE = (
    "You are a subagent. The session id is 7f3a91c4-2b18-4d5e-9a10-c8e2b6d43f70. "
    "Call the tool exactly once and return only what it gives you. "
)


def test_same_seed_and_text_always_produce_the_same_name() -> None:
    first = generate_agent_name("session-a", "deal the encounter cards")
    second = generate_agent_name("session-a", "deal the encounter cards")
    assert first == second


def test_different_seeds_produce_different_codenames() -> None:
    names = {generate_agent_name(f"session-{index}") for index in range(40)}
    # 32 adjectives x 32 nouns; 40 seeds must not collapse onto a handful.
    assert len(names) >= 35


def test_two_prompts_sharing_boilerplate_are_still_told_apart() -> None:
    first = generate_agent_name(
        "child-1", BOILERPLATE + "search_cards_marvel_champions for Spider-Man"
    )
    second = generate_agent_name(
        "child-2", BOILERPLATE + "search_cards_marvel_champions for Spider-Man"
    )
    assert first != second


def test_topic_is_taken_from_the_prompt_not_its_boilerplate() -> None:
    name = generate_agent_name("child-1", BOILERPLATE + "shuffle the villain deck")
    assert "shuffle" in name
    assert "villain" in name
    assert "subagent" not in name.lower()
    assert "session" not in name.lower()


def test_tool_names_contribute_their_words() -> None:
    name = generate_agent_name("child-1", "call search_cards_marvel_champions now")
    assert "search cards marvel" in name


def test_identifiers_and_numbers_are_not_used_as_topic_words() -> None:
    name = generate_agent_name(
        "child-1", "move 01001a to 7f3a91c4 in group player1Play 42 times"
    )
    assert "01001a" not in name
    assert "7f3a91c4" not in name
    assert "42" not in name
    assert "move" in name


def test_codename_alone_when_the_prompt_has_no_content_words() -> None:
    name = generate_agent_name("child-1", "you must use the tool and return it")
    assert " · " not in name
    assert name.split(" ") == name.split(" ")  # two words, no separator
    assert len(name.split(" ")) == 2


def test_no_text_yields_a_codename() -> None:
    assert " · " not in generate_agent_name("child-1")
    assert " · " not in generate_agent_name("child-1", "")
    assert " · " not in generate_agent_name("child-1", None)


def test_repeated_words_do_not_consume_the_whole_topic() -> None:
    name = generate_agent_name("child-1", "villain villain villain villain deck")
    assert name.count("villain") == 1
    assert "deck" in name


def test_name_is_bounded_for_a_very_long_prompt() -> None:
    prompt = "encounter " * 4000
    name = generate_agent_name("child-1", prompt)
    assert len(name) <= MAX_GENERATED_NAME_CHARS
    # A single repeated word still only earns one slot in the topic.
    assert name.count("encounter") == 1


def test_name_is_bounded_for_a_prompt_of_many_long_words() -> None:
    prompt = " ".join(f"decision{index}" for index in range(500))
    assert len(generate_agent_name("child-1", prompt)) <= MAX_GENERATED_NAME_CHARS


def test_topic_never_ends_mid_word() -> None:
    prompt = "encounter villain scheme threat acceleration retaliate boost"
    name = generate_agent_name("child-1", prompt)
    _, _, topic = name.partition(" · ")
    for word in topic.split(" "):
        assert word in prompt


def test_codename_is_two_capitalised_words() -> None:
    codename = generate_agent_name("child-1", "draw a card").split(" · ")[0]
    adjective, noun = codename.split(" ")
    assert adjective[0].isupper()
    assert noun[0].isupper()


def test_opaque_letter_runs_are_not_mined_for_words() -> None:
    """A credential-shaped string must not contribute fragments to a name."""
    name = generate_agent_name(
        "child-1", "authorization Bearer sk-proj-AbCdEfGhIjKl draw a card"
    )
    assert "abcdefghijkl" not in name.lower()
    assert "AbCdEfGh" not in name
    assert "draw card" in name


def test_group_and_card_identifiers_are_dropped_whole() -> None:
    name = generate_agent_name(
        "child-1", "move card 01001a from player1Play to sharedVillain discard"
    )
    lowered = name.lower()
    assert "player" not in lowered
    assert "shared" not in lowered
    assert "villain" not in lowered
    assert "move card" in lowered


def test_ordinary_capitalisation_still_reads_as_words() -> None:
    name = generate_agent_name("child-1", "Deal an encounter card to Rhino")
    assert "deal encounter card rhino" in name
