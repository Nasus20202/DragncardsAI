# Attach skills from the chat composer via @-mention

## Why

Attaching a skill to a Play session today means leaving the conversation: open
the right-hand settings panel, find the skill in the toggle list, flip it, and
press Save. The decision to bring a skill in is almost always made *while*
writing the message that needs it ("okay, now play the villain phase" — that
wants the Marvel Champions play skill), so the settings-panel round trip
interrupts exactly the moment it is needed.

The composer already owns that moment. Typing `@` there is the established
convention for "pull something into this message", and the dashboard already has
every piece required: the session's available skills are loaded on the workspace's
initial load, and `POST/DELETE /sessions/{id}/skills` already persists a session's
skill assignment.

## What Changes

- **dashboard (composer)** — typing `@` in the Play prompt box opens a picker over
  the composer listing the skills available to the session, filtered by whatever
  is typed after the `@`. Choosing one attaches it to the session and removes the
  `@…` token from the message text, because the skill is then represented by a
  chip rather than by prose in the prompt.
- **dashboard (composer)** — the skills currently attached to the session render as
  chips on the composer, each with a control that detaches it.
- **dashboard (skill assignment)** — attaching and detaching from the composer drive
  the *same* session skill assignment the settings panel's skill toggles drive:
  the composer's chips and the settings panel's toggles read one value, and a
  change made in either place is visible in the other immediately. Attaching from
  the composer persists straight away through the orchestrator's session skill
  endpoints, the way the MCP toggles already do, rather than waiting for a Save.
- **dashboard (filtering)** — the picker narrows its list with the same
  case-insensitive substring match the shared searchable model picker uses, so the
  two behave alike.

## Non-goals

- No per-player or per-agent addressing. The `@` in the original note ("`@player ?`")
  was uncertainty about the trigger character, not a request to address a seat;
  mentions attach skills to the session and nothing else.
- No context-management work (a separate change).
- No agent-orchestrator change. The session skill endpoints already register
  on-disk skills on enable and treat disable as idempotent, which is everything
  the composer needs.
- No restyling of the composer, the transcript, or the settings panel. The
  composer gains a chip row and a picker above it; nothing existing is
  re-laid out.
- The picker does not create skills, only assigns ones already on disk.
