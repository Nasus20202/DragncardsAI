# Tasks

## 1. Neutral state API and session propagation

- [x] 1.1 Add optional `player_n` to `get_game_state` while retaining operation ID `get_game_state`
- [x] 1.2 Make omission an explicit spectator/public projection rather than an implicit `player1`
- [x] 1.3 Add `Cache-Control: private, no-store` to projected state responses
- [x] 1.4 Forward the requested seat through `GameSession.get_state`, fresh retrieval, and normalization

## 2. Marvel transport and projection

- [x] 2.1 Validate an explicit Marvel seat against `held_seats` before engine access
- [x] 2.2 Forward the requested seat to Marvel world retrieval while retaining fallback only for transport access
- [x] 2.3 Make Marvel normalization stateless per call and preserve the neutral vocabulary
- [x] 2.4 Enforce engine ACL visibility and fail closed for malformed or ambiguous metadata
- [x] 2.5 Keep DragnCards state retrieval and normalization behavior unchanged

## 3. History and regression coverage

- [x] 3.1 Normalize Marvel durable history with spectator redaction
- [x] 3.2 Add API/MCP schema, cache-control, and omission tests
- [x] 3.3 Add seat visibility matrix, sequential cache-isolation, transport, unheld-seat, and ACL tests
- [x] 3.4 Add history-redaction and DragnCards regression coverage

## 4. Verification and delivery

- [x] 4.1 Run focused game-service unit tests for the changed state and Marvel paths
- [x] 4.2 Run game-service formatting and static checks practical in this lane
- [x] 4.3 Validate this OpenSpec change without archiving it
- [x] 4.4 Commit the coherent DRA-73 implementation on `task/dra-73-expose-marvel-hand`

## 5. Pre-integration corrections

- [x] 5.1 Let Marvel hand ACLs reveal owner names even when the engine reports hand cards as face down, with owner/other-seat/spectator regression coverage
- [x] 5.2 Teach the player skill to pass its assigned `player_n` on every state read and add an agent-facing guidance regression
- [x] 5.3 Restrict fresh-read bypass to reader-sensitive platforms and cover the ignored-selector DragnCards cache path with a real driver regression
- [x] 5.4 Replace the simplified-game-state OpenSpec requirement and update broad state guidance without changing the DRA-75 boundary
