## ADDED Requirements

### Requirement: Cross-game evaluation request listing
The eval-service SHALL expose an endpoint to list evaluation requests across all games,
ordered newest-first, so a client can present a persistent queue of in-progress and recent
evaluations without knowing each `request_id` in advance. Each listed request SHALL be
summarized with its `request_id`, `game_id`, overall status (derived from its targets),
`created_at`, and a per-target summary carrying at least each target's `scope`, `target_seq`,
`round_span`, and `status`. The endpoint SHALL support filtering to active requests (those
with at least one non-terminal target) and SHALL bound the number of returned requests with a
capped `limit`. The listing SHALL be derived from durable storage, not from any in-memory queue.

#### Scenario: List recent requests across games
- **WHEN** a client requests the evaluation list
- **THEN** the eval-service SHALL return the recent evaluation requests across all games ordered
  newest-first, each with its overall status and per-target scope/seq/round_span/status summary

#### Scenario: Filter to active requests
- **WHEN** a client requests the evaluation list with the active filter enabled
- **THEN** the eval-service SHALL return only requests that have at least one non-terminal target,
  omitting requests whose targets are all completed/skipped/failed/cancelled

#### Scenario: Bounded result size
- **WHEN** a client requests the evaluation list with a `limit` larger than the allowed maximum
- **THEN** the eval-service SHALL return no more than the capped maximum number of requests

### Requirement: Clearing terminal evaluation requests
The eval-service SHALL expose endpoints to clear evaluation requests from its queue tracking,
both individually and in bulk. A request MAY be cleared ONLY when it is fully terminal (no target
is still pending or running); a request with a non-terminal target SHALL NOT be cleared (it can
only be cancelled). Clearing SHALL remove only the eval-service's own request and target tracking
rows; verdicts already recorded as history-service events are independent and SHALL NOT be
affected. These endpoints are cross-game (not nested under `/games/{game_id}`).

#### Scenario: Delete a terminal request
- **WHEN** a client requests deletion of an evaluation request whose targets are all terminal
- **THEN** the eval-service SHALL remove that request and its target rows and SHALL no longer
  return it from the cross-game listing or the per-request lookup

#### Scenario: Reject deleting a non-terminal request
- **WHEN** a client requests deletion of an evaluation request that still has at least one
  pending or running target
- **THEN** the eval-service SHALL reject the request with a conflict (HTTP 409) and SHALL leave
  the request and its targets unchanged

#### Scenario: Delete a request that does not exist
- **WHEN** a client requests deletion of an unknown `request_id`
- **THEN** the eval-service SHALL respond with not found (HTTP 404)

#### Scenario: Clear all terminal requests
- **WHEN** a client requests a bulk clear of the evaluation queue
- **THEN** the eval-service SHALL remove every request that has no non-terminal target, SHALL
  leave requests with a pending or running target intact, and SHALL return the count of requests
  deleted
