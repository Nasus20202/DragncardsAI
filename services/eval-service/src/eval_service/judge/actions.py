"""Classification of recorded agent actions as strategic or non-strategic.

An `agent_move` history event records the MCP tool the playing agent called
(``payload.intended_action`` is the tool's own name, e.g. ``move_card``). Not
every such call is a play a judge can grade: some commit no game state at all
(searching the card database), some are session plumbing, and some establish the
starting position rather than playing from it.

The dividing line is deliberately **not** "does the tool read or write" but
**does the action commit game state in a way a player could get wrong**.
Searching for a card cannot be a wrong decision; taking a card into hand can be.
So ``search_cards_marvel_champions`` is non-strategic while ``draw_card`` and
``move_card`` are strategic even though all three merely "look at cards".

Classification is conservative by construction: an action is non-strategic ONLY
if it appears in the configured set, and anything unrecognised — a new tool, a
tool from another MCP server, a legacy action name — is treated as strategic and
evaluated. Wrongly skipping a strategic action silently degrades evaluation
quality in a way nobody notices; wrongly evaluating a trivial one only costs a
judge call.
"""

from __future__ import annotations

import json

from eval_service.schemas.history import (
    PLATFORM_DRAGNCARDS,
    PLATFORM_MARVEL_LCG,
    Platform,
)

# Reason categories, recorded verbatim in a skipped target's reason so a skipped
# action can never be mistaken for a passed one.
READ_ONLY = "read-only query; commits no game state, so it cannot be a wrong play"
SESSION_PLUMBING = (
    "session/room plumbing; creates, attaches to or deletes a room rather than "
    "playing a position"
)
PRE_GAME_SETUP = (
    "pre-game setup; establishes the starting position (seats, decks, card pool) "
    "rather than playing from it"
)

#: Read-only tools. They return information and change nothing on the table, so
#: there is no decision for a judge to grade. This is the category the reporter
#: named directly: "searching for cards is something that cannot be a wrong
#: decision".
_READ_ONLY_ACTIONS: dict[str, str] = {
    "get_game_state": READ_ONLY,
    "get_session_actions": READ_ONLY,
    "list_actions": READ_ONLY,
    "list_card_providers": READ_ONLY,
    "list_games": READ_ONLY,
    "lookup_session_by_slug": READ_ONLY,
    "search_cards_marvel_champions": READ_ONLY,
    "search_prebuilt_sets_marvel_champions": READ_ONLY,
}

#: Room/session lifecycle. Outside the game entirely.
_SESSION_ACTIONS: dict[str, str] = {
    "attach_game": SESSION_PLUMBING,
    "create_game": SESSION_PLUMBING,
    "delete_game": SESSION_PLUMBING,
}

#: Setup that builds the starting position. Deck and seat configuration is a
#: construction decision, not a play: none of the rubric's criteria
#: (rules legality of a play, tempo, threat/resource management) apply to it, and
#: in this system the deck comes from the user's request rather than from in-game
#: strategy. This is the most debatable group, which is exactly why it is
#: configurable -- move any entry back into evaluation with one setting.
_SETUP_ACTIONS: dict[str, str] = {
    "load_cards": PRE_GAME_SETUP,
    "load_prebuilt_deck": PRE_GAME_SETUP,
    "multiple_double_sided_villains": PRE_GAME_SETUP,
    "set_player_count_action": PRE_GAME_SETUP,
    "unload_cards": PRE_GAME_SETUP,
}

#: The built-in non-strategic taxonomy, keyed by action name.
#:
#: Everything else the game-service exposes is STRATEGIC and evaluated:
#: ``deal_encounter``, ``discard_minion``, ``discard_side_scheme``,
#: ``draw_boost``, ``draw_card``, ``exhaust_card``, ``flip_card``,
#: ``modify_tokens``, ``move_card``, ``mulligan_draw_hand``, ``next_step``,
#: ``player_end_phase``, ``prev_step``, ``ready_card``, ``raw_action``,
#: ``set_card_property``, ``shadows_of_the_past``, ``shuffle_into_deck``,
#: ``villain_encounter_phase``, ``villain_end_phase``, ``zero_tokens``.
#:
#: Several of those are borderline -- readying a card, zeroing tokens and the
#: phase-advance tools are largely mechanical -- but each commits game state that
#: a player can get wrong (readying the wrong card, ending the player phase with
#: actions unspent), so they stay evaluated.
NON_STRATEGIC_ACTION_REASONS: dict[str, str] = {
    **_READ_ONLY_ACTIONS,
    **_SESSION_ACTIONS,
    **_SETUP_ACTIONS,
}

#: Default value of the ``EVAL_NON_STRATEGIC_ACTIONS`` setting: the taxonomy
#: above as a comma-separated list, so the default is visible in configuration
#: and an operator replaces it by listing exactly the actions they want skipped.
DEFAULT_NON_STRATEGIC_ACTIONS = ",".join(sorted(NON_STRATEGIC_ACTION_REASONS))

# The DragnCards taxonomy is keyed by its MCP tool name. marvel-lcg has no tool
# name for a move: its durable identity is the engine option's id, name, and the
# event/prompt that offered it. The configured marvel set is intentionally empty;
# an unknown option is evaluated rather than silently skipped.
PLATFORM_NON_STRATEGIC_TAXONOMY: dict[Platform, dict[str, str]] = {
    PLATFORM_DRAGNCARDS: NON_STRATEGIC_ACTION_REASONS,
    PLATFORM_MARVEL_LCG: {},
}


def normalize_action_name(action: object) -> str:
    """Reduce a recorded ``intended_action`` to a bare tool name.

    Recorded values are the MCP server's own tool names, but a client may expose
    them under a namespaced alias (``mcp__game-service__move_card``,
    ``game_service_move_card``). Only the well-known ``mcp__<server>__`` form is
    unwrapped: guessing at arbitrary prefixes risks matching a DIFFERENT tool
    that merely ends in a known name, and an unmatched name is evaluated (the
    safe direction) rather than skipped.
    """
    if not isinstance(action, str):
        return ""
    name = action.strip()
    if name.startswith("mcp__"):
        name = name.rpartition("__")[2]
    return name


def non_strategic_reason(
    action: object,
    skip_actions: frozenset[str],
    platform: Platform = PLATFORM_DRAGNCARDS,
) -> str | None:
    """Return why ``action`` is non-strategic, or None when it must be evaluated.

    ``skip_actions`` is the operator-configured set. An action outside it — every
    unrecognised name included — returns None and is evaluated.
    """
    if platform == PLATFORM_MARVEL_LCG:
        name = option_identity_key(action)
    else:
        name = normalize_action_name(action)
    if not name or name not in skip_actions:
        return None
    reason = PLATFORM_NON_STRATEGIC_TAXONOMY.get(platform, {}).get(name)
    if reason is None:
        # Configured by an operator beyond the built-in taxonomy: still skipped,
        # but the reason says so rather than inventing a justification.
        return "configured as non-strategic"
    return reason


def parse_action_set(raw: str) -> frozenset[str]:
    """Parse taxonomy entries without splitting commas inside JSON identities.

    Operators may configure a marvel-lcg identity as a JSON object, for example
    ``{"id":7,"name":"Play","event":"Player Turn"}``. A plain ``split``
    would turn that one identity into several unrelated entries. Delimiters are
    therefore recognised only outside JSON strings and containers.
    """
    entries: list[str] = []
    start = 0
    depth = 0
    quote = False
    escaped = False
    for index, char in enumerate(raw):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quote = False
            continue
        if char == '"':
            quote = True
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth = max(0, depth - 1)
        elif char in ",;" and depth == 0:
            entries.append(raw[start:index].strip())
            start = index + 1
    entries.append(raw[start:].strip())

    result: set[str] = set()
    for entry in entries:
        if not entry:
            continue
        try:
            parsed = json.loads(entry)
        except TypeError, ValueError:
            result.add(entry)
            continue
        if isinstance(parsed, list):
            for item in parsed:
                result.add(_taxonomy_entry_key(item))
        else:
            result.add(_taxonomy_entry_key(parsed))
    return frozenset(result)


def option_identity_from_payload(payload: object) -> object:
    """Read and normalize the additive marvel option identity from a payload.

    ``marvel_lcg_option`` is the producer's field. The two ``option_identity``
    locations are accepted as compatible aliases from the earlier contract.
    ``intended_action`` remains the DragnCards compatibility field. The option
    identity is deliberately separate so a producer can add it without changing
    the meaning of existing move records.
    """
    if not isinstance(payload, dict):
        return None
    arguments = payload.get("arguments")
    candidates = [
        payload.get("marvel_lcg_option"),
        payload.get("option_identity"),
    ]
    if isinstance(arguments, dict):
        candidates.extend(
            (arguments.get("marvel_lcg_option"), arguments.get("option_identity"))
        )
    for candidate in candidates:
        identity = _canonical_option_identity(candidate)
        if identity is not None:
            return identity
    return None


def recorded_action(payload: object, platform: Platform) -> object:
    """Return the platform's durable action identity for judge input."""
    if not isinstance(payload, dict):
        return None
    if platform == PLATFORM_MARVEL_LCG:
        identity = option_identity_from_payload(payload)
        if identity is not None:
            return identity
    return payload.get("intended_action")


def option_identity_key(action: object) -> str:
    """Canonical id+name+event key for a marvel-lcg option.

    Accept both the documented object and a JSON string so older transport
    adapters cannot make a configured option unrecognisable. Names are never used
    alone: two options called ``Play`` remain two taxonomy entries.
    """
    normalized = _canonical_option_identity(action)
    if normalized is None:
        return ""
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def _canonical_option_identity(value: object) -> dict[str, object] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except TypeError, ValueError:
            return None
    if not isinstance(value, dict):
        return None
    nested = value.get("option_identity")
    if nested is not None:
        value = nested
    if not isinstance(value, dict):
        return None

    def first_present(*keys: str) -> object:
        for key in keys:
            if value.get(key) is not None:
                return value[key]
        return None

    normalized = {
        "event": first_present("event", "event_name", "event_type"),
        "id": first_present("id", "option_id"),
        "name": first_present("name", "option_name"),
    }
    if any(item is None for item in normalized.values()):
        return None
    return normalized


def _taxonomy_entry_key(value: object) -> str:
    if isinstance(value, dict):
        return option_identity_key(value)
    return str(value).strip()
