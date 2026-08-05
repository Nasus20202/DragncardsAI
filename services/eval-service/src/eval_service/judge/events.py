"""What a recorded history event *is*, read off the event itself.

Everything here answers a question about one stored event — is it a move, what
orchestration mode did it come from — in exactly one place, so no two call sites
can answer it differently.

## Why ``actor == "agent"`` is not "this is a move"

The ``agent`` actor means "the agent orchestrator produced this", not "the agent
played this". The orchestrator records other things about a game under that same
actor, starting with the ``illegal_action`` findings it writes when a seat's
action broke the rules. It has no choice about the actor: history-service's
envelope pins ``actor`` to a fixed ``Literal`` of
``agent``/``game-service``/``evaluator``/``user``, so a new producer concern
arrives as a new *event type* under an existing actor.

That makes ``actor == "agent"`` a strictly widening test over time, and every
place that used it to mean "a move" was one new event type away from being wrong
in an expensive way: a finding picked up as a move would be sent to the judge and
graded as a play, attributed to a seat as that seat's action, counted into a
round's move total, and — because a round's span is bounded by its moves — able to
shift a round boundary. :func:`is_agent_move` is the single predicate that
replaces it, and it is an allowlist of move event types rather than a denylist of
everything else, so the next event type the orchestrator adds is excluded by
default rather than silently graded.
"""

from __future__ import annotations

from eval_service.schemas.history import StoredEvent

#: The actor every agent-orchestrator event carries. Necessary for a move, not
#: sufficient — see the module docstring.
AGENT_ACTOR = "agent"

#: Event types that record a play by the agent, i.e. the events a judge grades.
#: ``agent_move`` is what the orchestrator emits for a game-mutating tool call;
#: ``agent_decision`` is the same shape under an alternative type name, accepted
#: so a producer that labels a decision rather than a move is still graded.
AGENT_MOVE_EVENT_TYPES = frozenset({"agent_move", "agent_decision"})

#: An orchestrator-recorded finding that a seat's action violated the rules. An
#: agent event, deliberately not a move: it is evidence *about* play rather than
#: play itself.
ILLEGAL_ACTION_EVENT_TYPE = "illegal_action"

#: Resolution states a finding is recorded in. A resolved finding stays on the
#: timeline — that the seat undid the action is part of the record, not a reason
#: to erase it — so a reader must distinguish the two rather than assume any
#: finding present is outstanding.
ILLEGAL_ACTION_STATUS_OPEN = "open"
ILLEGAL_ACTION_STATUS_RESOLVED = "resolved"

#: Orchestration modes an event can state it came from.
SESSION_MODE_CHAT = "chat"
SESSION_MODE_ORCHESTRATED = "orchestrated"


def is_agent_move(event: StoredEvent) -> bool:
    """Whether ``event`` is a play by the agent — the thing a judge grades.

    Requires both the ``agent`` actor and a move event type. Use this anywhere a
    move is being selected, counted, attributed, spanned or graded; never test
    the actor alone (see the module docstring for what that costs).
    """
    return event.actor == AGENT_ACTOR and event.event_type in AGENT_MOVE_EVENT_TYPES


def is_illegal_action_finding(event: StoredEvent) -> bool:
    """Whether ``event`` is an orchestrator-recorded illegal-action finding."""
    return event.actor == AGENT_ACTOR and event.event_type == ILLEGAL_ACTION_EVENT_TYPE


def session_mode_of(event: StoredEvent) -> str:
    """The orchestration mode ``event`` states it came from, defaulting to ``chat``.

    The orchestrator omits the key for chat mode rather than writing ``"chat"``,
    so an absent key and a chat-mode session are the same thing — as is every
    event recorded before the mode existed. An unrecognised value also reads as
    chat: a mode this service does not know is not one it can project honestly.
    """
    value = event.payload.get("session_mode")
    if value == SESSION_MODE_ORCHESTRATED:
        return SESSION_MODE_ORCHESTRATED
    return SESSION_MODE_CHAT


def span_session_mode(events: list[StoredEvent], from_seq: int, to_seq: int) -> str:
    """The orchestration mode of the play recorded in ``[from_seq, to_seq]``.

    Read from the agent events in the span. They are the events whose mode a
    projection turns on, and reading them alone means the answer never depends on
    whether a user prompt happened to land inside these bounds.

    A single orchestrated event decides the span: the seats of an orchestrated
    table each held their own context regardless of how many of them happened to
    act inside these bounds, and a judge told otherwise would grade a seat on
    information it never had. A span with no agent events at all is chat, which is
    the same answer the default gives everywhere else.
    """
    return (
        SESSION_MODE_ORCHESTRATED
        if any(
            event.actor == AGENT_ACTOR
            and from_seq <= event.seq <= to_seq
            and session_mode_of(event) == SESSION_MODE_ORCHESTRATED
            for event in events
        )
        else SESSION_MODE_CHAT
    )
