## MODIFIED Requirements

### Requirement: Persistent evaluations queue
The dashboard SHALL provide a persistent evaluations queue in the History tab that is
accessible at all times (independent of the selected game and of the per-game Evaluate
drawer), showing the in-progress and recent evaluations across all games. Each queue entry
SHALL show the game (by its friendly name when known), a scope label distinguishing the
evaluation's scope (move / round / range / whole game), and the current status/progress, and
SHALL offer a Cancel action while the request is non-terminal. The queue SHALL reflect status
changes over time (by polling the eval-service listing) and SHALL surface an active-count
indicator so the user can tell, without opening it, that evaluations are running.

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
