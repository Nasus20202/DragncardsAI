## Why

Player-seat authorization currently trusts identity metadata on a child session and only checks whether the referenced orchestrator is in orchestrated mode. A caller that can create or update a session can therefore forge a seat identity without being registered on the orchestrator's roster. Persistent seat assignment also uses a read-then-write sequence, so concurrent prompts can race to replace the seat's durable child session.

## What Changes

- Remove server-owned player identity fields from public session metadata before persistence.
- Require a seat session's player id and session id to match the orchestrator's persisted player configuration before granting seat identity.
- Claim a persistent seat with one conditional database update so an existing child session cannot be replaced by a racing prompt.
- Add regression coverage for forged metadata, unregistered seat sessions, and repeated seat claims.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-orchestrator`: bind player identity to the persisted roster and make persistent seat ownership race-safe.

## Non-goals

- Changing the player-agent tool allowlist or platform ownership rules.
- Changing `wait_for_subagent` ownership checks or cross-game session binding; those are separate security findings.
- Changing the public shape of legitimate server-created seat metadata.
