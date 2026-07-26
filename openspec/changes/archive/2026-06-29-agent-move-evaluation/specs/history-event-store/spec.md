## MODIFIED Requirements

### Requirement: Versioned event envelope
The history-service SHALL define a versioned event envelope containing an envelope version, a game correlation identifier (`game_id`), an actor of `agent`, `game-service`, or `evaluator`, an event type, a JSON payload, a producer-supplied occurrence timestamp, an idempotency key, and a history-assigned monotonic per-game sequence number and recorded timestamp.

#### Scenario: Accept a well-formed envelope
- **WHEN** a producer submits an event envelope containing `envelope_version`, `game_id`, `actor`, `event_type`, `payload`, `occurred_at`, and `idempotency_key`
- **THEN** the history-service SHALL accept the envelope and SHALL assign a monotonic per-game `seq` and a `recorded_at` timestamp before persisting it

#### Scenario: Reject an envelope missing required fields
- **WHEN** a producer submits an envelope missing `game_id`, `actor`, or `event_type`
- **THEN** the history-service SHALL reject the envelope with a validation error and SHALL NOT persist any event

#### Scenario: Accept the evaluator actor
- **WHEN** a producer submits an envelope whose `actor` is `evaluator`
- **THEN** the history-service SHALL accept the envelope and SHALL persist it with the same ordering and idempotency rules as `agent` and `game-service` events

#### Scenario: Reject an unknown actor
- **WHEN** a producer submits an envelope whose `actor` is none of `agent`, `game-service`, or `evaluator`
- **THEN** the history-service SHALL reject the envelope with a validation error and SHALL NOT persist any event

#### Scenario: Tolerate unknown forward-compatible fields
- **WHEN** a producer submits an envelope with a recognized `envelope_version` and additional unknown fields
- **THEN** the history-service SHALL persist the envelope without failing on the unknown fields

#### Scenario: Evaluator events are not replayed as game mutations
- **WHEN** the history-service replays events forward during a restore
- **THEN** it SHALL NOT apply `evaluator` events as game mutations, treating them as advisory like `agent` events
