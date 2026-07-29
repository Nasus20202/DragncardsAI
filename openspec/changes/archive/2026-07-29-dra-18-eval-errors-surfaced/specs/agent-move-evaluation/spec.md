## MODIFIED Requirements

### Requirement: Failure isolation from ingestion and play
The eval-service SHALL never block, fail, or slow history ingestion or game play. When a judge call fails or times out, the eval-service SHALL retry up to a configured attempt limit and then record the target as `failed` carrying the reason, acknowledging or dead-lettering the queue entry, so that a failing target does not stall the queue.

A failure SHALL NOT be recorded as `skipped`. `skipped` SHALL mean only that the target carried no decision a judge could grade, so a client can always distinguish an error from a deliberate skip. Every error path — judge attempts exhausted, an assembly error, an undetectable round boundary, an unreadable recorded timeline, a failed verdict write-back, and no configured judge model — SHALL record `failed` with its reason.

#### Scenario: Judge failure results in a failed target with its reason
- **WHEN** a judge call for a target fails repeatedly up to the configured attempt limit
- **THEN** the eval-service SHALL record that target as `failed` carrying the reason for the failure, SHALL NOT write a verdict for it, and SHALL continue processing subsequent targets without stalling the queue

#### Scenario: An error is never reported as a skip
- **WHEN** a target fails for any reason — the judge, assembly, round-boundary detection, the history read, the verdict write-back, or a missing judge model
- **THEN** its terminal status SHALL be `failed` and SHALL NOT be `skipped`, so it cannot be confused with a deliberately skipped non-strategic action

#### Scenario: Ingestion and play unaffected by judge outage
- **WHEN** the judge is unavailable while games continue to be played and recorded
- **THEN** history ingestion and game play SHALL proceed unaffected because the eval-service consumes a copy of already-committed events and only writes advisory evaluator events

### Requirement: Non-strategic actions are skipped with a recorded reason
The eval-service SHALL NOT spend a judge call on a recorded action that commits no game state a player could get wrong. The classification SHALL turn on whether the action commits game state in a way a player could get wrong, NOT on whether the underlying tool reads or writes: searching a card database cannot be a wrong decision, whereas taking a card into hand can be, so a search SHALL be treated as non-strategic while drawing or playing a card SHALL be evaluated.

The set of non-strategic actions SHALL be operator-configurable, and its default SHALL cover read-only queries, session and room plumbing, and pre-game setup that establishes the starting position. Any action outside the configured set — including every action name the service does not recognise — SHALL be evaluated, so that a new or renamed action can never be skipped by accident.

A skipped non-strategic target SHALL be recorded as `skipped` carrying a reason that names the action and why it was skipped, and SHALL NOT be recorded as completed and SHALL NOT have a verdict written to history. The `skipped` status SHALL be reserved for this deliberate skip: a target that FAILED is recorded as `failed`, so a client can present a skip and an error differently. Skipping SHALL be possible to disable entirely by configuration.

A round-level or game-level roll-up SHALL exclude non-strategic moves from the moves it grades and SHALL state how many were excluded, so a roll-up score is not influenced by ungradeable actions. A roll-up whose span contains only non-strategic moves SHALL still be produced; the skip is a move-level judgement.

#### Scenario: Searching for a card is skipped, taking one into hand is not
- **WHEN** the eval-service evaluates a recorded move whose action is a card or set search
- **THEN** it SHALL record the target as `skipped` with a reason naming the action, SHALL NOT invoke the judge, and SHALL NOT write a verdict
- **AND WHEN** the recorded move's action instead draws a card into hand or plays a card
- **THEN** the eval-service SHALL evaluate it normally

#### Scenario: A skipped action cannot be mistaken for a passing verdict
- **WHEN** a client inspects an evaluation request that contained non-strategic targets
- **THEN** each such target SHALL appear with terminal status `skipped` and its stated reason, and SHALL NOT appear as completed or carry a score

#### Scenario: A skipped action cannot be mistaken for a failure either
- **WHEN** an evaluation request contains both a deliberately skipped non-strategic target and a target that failed
- **THEN** the skipped target SHALL carry status `skipped` and the failed target status `failed`, so a client can present the failure as a problem and the skip as routine

#### Scenario: Unrecognised action is evaluated
- **WHEN** a recorded move names an action the service's taxonomy does not know
- **THEN** the eval-service SHALL evaluate it rather than skip it

#### Scenario: Skip set is configurable in both directions
- **WHEN** an operator supplies an explicit set of non-strategic action names
- **THEN** that set SHALL replace the built-in default, so an action the default skipped is evaluated unless it is listed
- **AND WHEN** an operator disables non-strategic skipping
- **THEN** every recorded move SHALL be evaluated

#### Scenario: Roll-up states what it left out
- **WHEN** a round roll-up's span contains non-strategic moves
- **THEN** those moves SHALL be omitted from the moves the judge is asked to grade and the input SHALL state how many were omitted

### Requirement: Cross-game evaluation request listing
The eval-service SHALL expose an endpoint to list evaluation requests across all games,
ordered newest-first, so a client can present a persistent queue of in-progress and recent
evaluations without knowing each `request_id` in advance. Each listed request SHALL be
summarized with its `request_id`, `game_id`, overall status (derived from its targets),
`created_at`, and a per-target summary carrying at least each target's `scope`, `target_seq`,
`round_span`, `status`, and the recorded error detail of any target that has one — including a
target that is still in progress — so a client polling the listing can report a failure while
the request is running. The endpoint SHALL support filtering to active requests (those
with at least one non-terminal target) and SHALL bound the number of returned requests with a
capped `limit`. The listing SHALL be derived from durable storage, not from any in-memory queue.

#### Scenario: List recent requests across games
- **WHEN** a client requests the evaluation list
- **THEN** the eval-service SHALL return the recent evaluation requests across all games ordered
  newest-first, each with its overall status and per-target scope/seq/round_span/status summary

#### Scenario: Listing carries the error detail of an in-progress failure
- **WHEN** a client requests the evaluation list while a request has a still-running target whose
  last judge attempt failed
- **THEN** that target's summary SHALL carry the recorded error detail, so the client can report
  the failure without waiting for the request to reach a terminal status

#### Scenario: Filter to active requests
- **WHEN** a client requests the evaluation list with the active filter enabled
- **THEN** the eval-service SHALL return only requests that have at least one non-terminal target,
  omitting requests whose targets are all completed/skipped/failed/cancelled

#### Scenario: Bounded result size
- **WHEN** a client requests the evaluation list with a `limit` larger than the allowed maximum
- **THEN** the eval-service SHALL return no more than the capped maximum number of requests

## ADDED Requirements

### Requirement: Evaluation errors are reported live with redacted detail
The eval-service SHALL report an evaluation failure as it happens, not only when the target reaches a terminal state. Every failed judge attempt SHALL be recorded with its reason on the target while that target is still in progress, and SHALL be pushed to the live channel so a connected client learns of it immediately. A failure SHALL NOT be reported only through logs.

The recorded reason SHALL be held in durable storage (the service's PostgreSQL), never in process memory, so any replica, poller or stream reads the same detail. Reporting SHALL use the service's existing live channel and target-status projections; it SHALL NOT introduce a second transport.

A retry that eventually succeeds SHALL clear the recorded in-progress error, so a transient failure that was overcome is not left behind as a false failure on a completed target.

All error detail the eval-service records or serves SHALL be redacted and length-bounded before it is stored. Credentials SHALL NOT appear in it: authorization headers and bearer tokens, named gateway key headers, `api_key`/`access_token`/`client_secret`/`password`-style fields, and bare provider key literals SHALL be replaced with a redaction marker. The detail SHALL be truncated to a bounded length so a provider response echoing a full request body — the judge prompt and a recorded game state — can never be persisted or streamed. Redaction SHALL be applied at the storage boundary so no recording path can bypass it, and SHALL run before truncation so a secret beyond the cut cannot survive.

#### Scenario: A failed judge attempt is visible during the run
- **WHEN** a judge attempt for a target fails and the eval-service is about to retry it
- **THEN** the attempt's reason SHALL be recorded on that target in durable storage while the target's status is still in progress, the live channel SHALL be signalled, and a client reading the target's status (by stream or by polling) SHALL see the reason before the request reaches a terminal state

#### Scenario: A recovered retry leaves no false failure
- **WHEN** an earlier judge attempt failed and a later attempt for the same target succeeds
- **THEN** the target SHALL be recorded as completed with its verdict and SHALL NOT retain the earlier attempt's error detail

#### Scenario: Terminal failure detail reaches the client
- **WHEN** a target reaches a terminal `failed` state
- **THEN** its reason SHALL be included in the per-target results of the request-status endpoint, the cross-game listing, and the live stream's status snapshot

#### Scenario: Credentials are never present in error detail
- **WHEN** a gateway or transport failure message embeds an authorization header, a bearer token, a named key header, an api-key field, or a bare provider key literal
- **THEN** the eval-service SHALL replace each with a redaction marker before storing the detail, so no credential is written to storage or served to a client

#### Scenario: A provider echoing the request body is truncated
- **WHEN** an error message carries a provider response body far larger than the recorded-detail bound — for example one echoing the judge prompt and a recorded game state
- **THEN** the eval-service SHALL store and serve only a bounded excerpt, marked as truncated

#### Scenario: A secret beyond the truncation point is still redacted
- **WHEN** an error message carries a credential positioned past the length bound
- **THEN** that credential SHALL be redacted rather than merely cut off, so shortening the message cannot reveal it
