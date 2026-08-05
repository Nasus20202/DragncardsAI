# Say so when a session save did not take effect

## Why

DRA-53 reports that switching a session's allowed subagent persona and saving
resets the toggle to its previous state, and that the session persona picker does
the same.

The reported behaviour is real and was reproduced, but **not by a defect in this
tree**. It is what a current dashboard does when it is pointed at an
agent-orchestrator built before DRA-38. That server's `SessionUpdateRequest` has
no `session_persona` and no `allowed_subagents` field; Pydantic's default for an
unknown field is to ignore it, so the `PATCH` is answered `200 OK` with a session
body carrying neither field. The dashboard rebuilds its draft from that body,
`buildDraftFromSession` maps both absences to "empty" — which is exactly what they
mean when the server does support them — and the controls snap back. The status
line says **Configuration saved**.

Reproduced end to end against a pre-DRA-38 orchestrator: `PATCH` request body
carried `allowed_subagents: ["kawaii-girl"]`, the response was `200` with no
`allowed_subagents` and no `session_persona` key, and the toggle reverted. The
same click against a current orchestrator persists.

So the bug to fix is not the reverting toggle. It is that **the dashboard reports
a save it cannot show happened**. A save that silently discards a change is bad in
any case; on a security-shaped control — an allowlist of what the agent may spawn
— it is worse, because the user is left believing they narrowed something they did
not. Version skew is only the way this deployment reached that state; a server
that refuses, ignores, or partially applies a field for any other reason produces
the same lie.

The dashboard already re-reads the session after saving, so it holds both the
configuration it asked for and the configuration the server actually has. It
simply does not compare them.

## What Changes

### A save that did not take effect is reported as such

After `saveConfiguration` re-reads the session it already fetches, the settings it
asked the server to store are compared against the settings the server reports.
When a field the request named comes back holding something else — including
missing from the response altogether — the save is reported as **incomplete**
rather than saved: the status line says so and the error area names each setting
that did not stick, together with the most likely reason, which is that the
orchestrator is older than the dashboard talking to it.

Creating a session is deliberately left alone. Selecting the session just created
starts the session loader, which reports "Ready" and clears the error area the
moment it lands, so a message set on that path is one the user never gets to read.
The same loader re-seeds the panel from the created session, so a setting the
server dropped is shown as dropped rather than misreported, and the first save
then says so.

The compared fields are the session persona and the subagent allowlist. They are
the two settings whose absence from a response is indistinguishable from having
been cleared, which is what makes their loss silent; every other field the panel
writes is either echoed by servers old and new or has its own refusal path.

The draft is still re-seeded from what the server actually reports. Showing the
user a setting the server does not have would be the same lie in the other
direction — the panel must keep showing the truth, and say that the truth is not
what was asked for.

## Capabilities

### Modified Capabilities

- `dashboard` — saving or creating a session reports when the server did not apply
  a setting it was asked to store, instead of reporting success.

## Impact

- **dashboard** — `features/play/lib/session-draft.ts` gains the comparison,
  `features/play/lib/use-play-session-actions.ts` calls it when saving.
- **No orchestrator change.** The running orchestrator in the deployment that
  produced this report cannot be fixed by any commit; the client is the only side
  that can notice.
- **No behaviour change against a current orchestrator.** Every field round-trips,
  so the comparison finds nothing and the save reports success exactly as before.

## Operator note

The deployment that produced this report needs its agent-orchestrator image
rebuilt and restarted; its database has never run migration
`0013_session_persona_and_subagent_allowlist`, so the allowlist table does not
exist there. Rebuilding is the operator's call and is not part of this change.

## Non-goals

- **No rejection of unknown fields on the orchestrator.** Making
  `SessionUpdateRequest` refuse extra keys would turn the *next* skew of this kind
  into a `422` instead of silence, which is the right default — but it changes the
  HTTP contract for every client including the generated MCP surface, so it is a
  decision of its own rather than a rider on a bug fix.
- **No version negotiation between the dashboard and the orchestrator.** The
  comparison needs no version number: it checks the effect, not the identity, of
  the server, and so covers refusals that have nothing to do with skew.
- **No change to what the controls look like.** No restyling, no new control; the
  existing status and error areas carry the message.
- **No message on the create path.** Not an oversight: the session loader that
  runs immediately after clears it. Making that path report would mean stopping
  the loader from clearing an error it did not cause, which is a separate change.
