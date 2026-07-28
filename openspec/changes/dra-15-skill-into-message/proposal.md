# An @-mention loads the skill into the message it was typed in

## Why

DRA-11 gave the composer an `@` mention picker, and it reads as a *session
setting* rather than as part of the message: choosing a skill deletes the `@…`
token from the prompt, attaches the skill to the session, and a chip appears
below the textarea. The message the user was writing ends up with no trace of
the skill in it, and the agent still has to decide to call `load_skill` before
the skill's instructions are in its context — which it may not do on the turn
that needed them.

The reporter of DRA-15 expected the other thing, in their words: *"Importing the
skill with @ should load it into a message."* An `@` mention is the established
"pull this into this message" gesture, so the skill's own text belongs in the
turn the user typed it in, not only in a toggle list.

## What Changes

- **dashboard (composer)** — choosing a skill from the mention picker now
  *completes* the `@…` token into the full `@<skill-name>` token instead of
  deleting it. The mention stays visible in the message the user is writing and
  in the message they send, so what was pulled in is on the record.
- **dashboard (composer)** — the picker now offers skills already attached to the
  session too. DRA-11 hid them because a second mention had nothing left to do;
  now a second mention loads the skill into a second message, so hiding them
  would have emptied the picker exactly for the sessions that use skills most.
- **dashboard (send)** — submitting a prompt names the skills mentioned in it, so
  the orchestrator knows which ones this turn asked for. Only mentions that match
  a skill actually assigned to the session count; typed text that merely looks
  like a mention is left alone.
- **agent-orchestrator (prompt submission)** — `POST /sessions/{id}/prompts`
  accepts the skills a prompt loads inline, validates them against the skill
  roots, and records them on the job.
- **agent-orchestrator (prompt execution)** — the user message the model receives
  begins with the full `SKILL.md` content of each such skill — the same payload
  `load_skill` would have returned, reference inventory included — followed by
  what the user typed. The stored job prompt stays exactly what the user typed,
  so the transcript, the session name, and the replayed history are unchanged.
- **agent-orchestrator (visibility)** — each skill loaded this way emits the
  existing `skill_loaded` event, so the transcript shows "Skill loaded: <name>"
  for a mention exactly as it already does for a `load_skill` call.

## How this relates to DRA-11

DRA-11's session-level attach is **kept, not replaced**. An `@` mention now does
both: it assigns the skill to the session *and* loads that skill's text into the
message. Three reasons the assignment has to stay:

1. `load_skill_reference` and `load_skill` refuse a skill that is not assigned to
   the session. The inlined `SKILL.md` ends with an inventory of its reference
   files, and following that inventory is the whole point of the progressive
   disclosure design — without the assignment the agent would be handed a list of
   references it is forbidden to open.
2. The inlined text lives in one turn only: replay reconstructs a prior turn from
   the stored job prompt, which is the typed text. The assignment is what lets the
   agent re-load the skill on a later turn instead of losing it silently.
3. The settings panel's toggle list stays the single answer to "which skills does
   this session have", which is exactly what DRA-11 established.

So the composer keeps its chip row (session membership) and gains a durable
mention token in the message text (this turn's loaded content). They mean
different things and both are true at once.

## Non-goals

- No flag or setting to choose between the two behaviours. There is one behaviour.
- No mention-driven *un*loading. Deleting the token from an unsent message removes
  it from that turn; detaching from the session is still the chip's job.
- No re-inlining on later turns, and no inlining into replayed history. A mention
  costs its tokens once, on the turn it was typed.
- No skill content endpoint for the dashboard. Skill text stays server-side; the
  browser sends names, not bodies.
- No new dashboard component and no restyling. The picker, the chips, and the
  textarea look exactly as they do today.
- No change to how the system prompt advertises skills: it still carries summaries
  only, and `load_skill` remains the agent's own way in.
