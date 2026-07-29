# game-history-ui

## MODIFIED Requirements

### Requirement: Surface evaluator events and scores on the timeline
The dashboard SHALL surface `evaluator` events on the game history timeline, visually distinct from agent and game-service events, anchored to the move or round they grade, and SHALL show the verdict detail when an evaluator event is selected.

A verdict's scope label SHALL name what the verdict graded, and SHALL NOT present sequence numbers as round numbers. A round-scoped verdict SHALL be labelled with the round of play recorded on the verdict, using the same "Round N" wording and the same conversion as the transcript's round bands and navigation tree, so a verdict and the round band it sits inside cannot name the same round differently. The verdict's sequence span SHALL NOT be used to derive that number: the span is a pair of event sequences, and a span read as a round range labels a verdict covering sequences 1 to 63 as "Rounds 1–63".

A round verdict that carries no recorded round of play — a verdict written before the round of play was recorded, including every verdict from an earlier evaluator version whose spans were derived differently — SHALL be labelled by its scope alone, with no round number. The dashboard SHALL NOT resolve such a verdict's span against boundaries it detects itself, because a span derived under a superseded rule resolves to a round the verdict did not grade, which is indistinguishable from a correct label. The span SHALL remain visible in the verdict detail, presented as the sequences it is.

#### Scenario: Evaluator event anchored to the graded move or round
- **WHEN** the history view renders a game's timeline containing an `evaluator` event
- **THEN** the dashboard SHALL display that evaluator event anchored to the move (`target_seq`) or round (`round_span`) it grades, visually distinct from agent and game-service events

#### Scenario: A round verdict is labelled with its round of play
- **WHEN** the transcript renders a round-scoped verdict that records round of play 1 and a sequence span of 1 to 63
- **THEN** its scope label SHALL read "Round 1" and SHALL NOT read "Rounds 1–63"

#### Scenario: A round verdict with no recorded round is not given a number
- **WHEN** the transcript renders a round-scoped verdict that carries a sequence span but no round of play
- **THEN** its scope label SHALL name the scope without a round number, and SHALL NOT show a number taken from the span

#### Scenario: Show verdict detail for an evaluator event
- **WHEN** a user selects an `evaluator` event in the timeline
- **THEN** the dashboard SHALL display the per-criterion scores, the overall score, the rationale, and any flags from the verdict payload

#### Scenario: Timeline without evaluator events
- **WHEN** a game has no `evaluator` events yet
- **THEN** the dashboard SHALL render the timeline normally without an error and without claiming evaluations exist

### Requirement: Persistent evaluations queue
The dashboard SHALL provide a persistent evaluations queue in the History tab that is
accessible at all times (independent of the selected game and of the per-game Evaluate
drawer), showing the in-progress and recent evaluations across all games. Each queue entry
SHALL show the game (by its friendly name when known), a scope label distinguishing the
evaluation's scope (move / round / range / whole game), and the current status/progress, and
SHALL offer a Cancel action while the request is non-terminal. The queue SHALL reflect status
changes over time (by polling the eval-service listing) and SHALL surface an active-count
indicator so the user can tell, without opening it, that evaluations are running.

A queue entry identifies its targets by sequence, because that is what a queued target is keyed
by before it has been graded. Its scope labels SHALL therefore present sequences in a sequence
notation, and a round target's sequence span SHALL NOT be rendered as a range of round numbers.

A queue entry SHALL also show the failure detail of every target of that request that has one,
identified by the target it happened on, so a user can tell WHY an evaluation failed and not
merely that it did. This detail SHALL appear while the request is still running — the
eval-service records a failed judge attempt on the target as it happens — so a failure is
reported during the evaluation rather than only in its final status. The entry MAY cap how many
individual failures it lists provided it states how many more there are. A deliberately skipped
non-strategic target's reason SHALL NOT be presented as a failure, and neither SHALL the
bookkeeping reason of a cancelled target.

The queue SHALL obtain this detail from the evaluation listing it already polls; it SHALL NOT
open a second live connection for it.

#### Scenario: See in-progress evaluations across games
- **WHEN** the user opens the evaluations queue while evaluations are running for one or more games
- **THEN** the dashboard SHALL list those evaluations with their game, scope label, and live
  status, and SHALL keep the list updated as their status changes

#### Scenario: A round target is identified by its sequence span
- **WHEN** a queue entry labels a round target whose sequence span runs from 64 to 103
- **THEN** the label SHALL present that span in the entry's sequence notation and SHALL NOT read
  "Rounds 64–103"

#### Scenario: A failure is reported while the evaluation is still running
- **WHEN** a target of a queued evaluation has recorded a failure and the request has not yet
  reached a terminal status
- **THEN** the queue entry SHALL show that failure's detail alongside the target it happened on,
  on the queue's normal refresh, without waiting for the request to finish

#### Scenario: A terminal failure states its reason
- **WHEN** a queued evaluation ends with one or more failed targets
- **THEN** the queue entry SHALL show each failed target's reason, and SHALL NOT show only the
  request's overall status

#### Scenario: Many failures are summarized rather than dropped
- **WHEN** a queued evaluation has more failed targets than the entry lists individually
- **THEN** the entry SHALL show the listed failures and SHALL state how many further failures
  there are, so none of them is silently hidden

#### Scenario: A deliberate skip is not presented as a failure
- **WHEN** a queued evaluation contains a target skipped as a non-strategic action, carrying the
  reason for that skip
- **THEN** the queue entry SHALL NOT present that reason as a failure

#### Scenario: Cancel from the queue
- **WHEN** the user activates Cancel on a non-terminal evaluation in the queue
- **THEN** the dashboard SHALL request cancellation of that evaluation and reflect the resulting
  cancelled status in the queue

#### Scenario: Active-count indicator
- **WHEN** one or more evaluations are in progress
- **THEN** the dashboard SHALL show an active-count indicator on the queue control even while the
  queue panel is closed
