## 1. Coordination Store

- [x] 1.1 Add Valkey client configuration and connection settings to game-service.
- [x] 1.2 Move session registry reads and writes from in-memory storage to Valkey-backed coordination state.
- [x] 1.3 Ensure session create/delete flows update the Valkey coordination record atomically.

## 2. Runtime Recovery

- [x] 2.1 Rehydrate active session coordination data from Valkey during game-service startup.
- [x] 2.2 Verify session lookup, listing, and teardown work after a process restart.

## 3. Docker Compose

- [x] 3.1 Add a Valkey service to `docker-compose.infra.yaml` with local development defaults.
- [x] 3.2 Wire the infra startup script to bring up Valkey before the main stack.
- [x] 3.3 Wire game-service environment variables to the Valkey service and add dependency ordering.

## 4. Verification

- [x] 4.1 Add or update tests for session creation, deletion, and lookup against the Valkey-backed coordination store.
- [x] 4.2 Add restart-oriented integration coverage for recovering active sessions from Valkey.
