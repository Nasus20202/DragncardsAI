## 1. Authorization boundary

- [x] 1.1 Strip server-owned player identity metadata from public session create and update requests.
- [x] 1.2 Require the child session to be registered on the referenced orchestrator seat before resolving identity.

## 2. Persistent seat ownership

- [x] 2.1 Make the seat-session claim a conditional database update that cannot replace an existing owner.
- [x] 2.2 Preserve the existing reuse behavior after a seat has been claimed.

## 3. Verification

- [x] 3.1 Add API coverage for forged public metadata.
- [x] 3.2 Add identity coverage for an unregistered child session.
- [x] 3.3 Add repository/runtime coverage for a second claim losing without changing ownership.
- [x] 3.4 Run the service checks and OpenSpec validation.
