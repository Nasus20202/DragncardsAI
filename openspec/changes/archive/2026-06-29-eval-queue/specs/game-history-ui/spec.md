## ADDED Requirements

### Requirement: Persistent evaluations queue
The dashboard SHALL provide a persistent evaluations queue in the History tab that is
accessible at all times (independent of the selected game and of the per-game Evaluate
drawer), showing the in-progress and recent evaluations across all games. Each queue entry
SHALL show the game (by its friendly name when known), a scope label distinguishing the
evaluation's scope (move / round / range / whole game), and the current status/progress, and
SHALL offer a Cancel action while the request is non-terminal. The queue SHALL reflect status
changes over time (by polling the eval-service listing) and SHALL surface an active-count
indicator so the user can tell, without opening it, that evaluations are running.

#### Scenario: See in-progress evaluations across games
- **WHEN** the user opens the evaluations queue while evaluations are running for one or more games
- **THEN** the dashboard SHALL list those evaluations with their game, scope label, and live
  status, and SHALL keep the list updated as their status changes

#### Scenario: Cancel from the queue
- **WHEN** the user activates Cancel on a non-terminal evaluation in the queue
- **THEN** the dashboard SHALL request cancellation of that evaluation and reflect the resulting
  cancelled status in the queue

#### Scenario: Active-count indicator
- **WHEN** one or more evaluations are in progress
- **THEN** the dashboard SHALL show an active-count indicator on the queue control even while the
  queue panel is closed

### Requirement: Enqueue-and-watch evaluation submission
The dashboard Evaluate control SHALL act as a configure-and-submit step: the user selects the
scope and judge configuration and submits, which enqueues the evaluation request; the request
SHALL then appear in the persistent queue, and the user SHALL be able to close the Evaluate
control immediately without interrupting or losing visibility of the running evaluation. Live
progress, judge output, and cancellation for a submitted evaluation SHALL be observed in the
queue rather than requiring the Evaluate control to remain open.

#### Scenario: Submitting drops the evaluation into the queue
- **WHEN** the user submits an evaluation from the Evaluate control
- **THEN** the dashboard SHALL enqueue the request and show it in the persistent queue, and the
  Evaluate control MAY be closed without affecting the running evaluation

#### Scenario: Closing the Evaluate control does not lose the evaluation
- **WHEN** the user closes the Evaluate control while a submitted evaluation is still running
- **THEN** the evaluation SHALL continue and remain visible and cancelable in the persistent queue

### Requirement: Clearing evaluations from the queue
The dashboard SHALL let the user clear terminal evaluations from the persistent queue, both one at
a time and all at once. A Clear action SHALL be offered ONLY for a request that is fully terminal
(no target still in progress); a non-terminal request SHALL continue to offer Cancel instead of
Clear, so a running evaluation can never be cleared from the UI. A "Clear all" action SHALL clear
every terminal request and SHALL be disabled when there are no terminal requests. Clearing SHALL
remove entries from the queue view only and SHALL NOT affect verdicts already recorded in history.

#### Scenario: Clear a single terminal evaluation
- **WHEN** the user activates Clear on a terminal evaluation in the queue
- **THEN** the dashboard SHALL request its deletion and the entry SHALL no longer appear in the
  queue after the listing refreshes

#### Scenario: Clear is not offered for running evaluations
- **WHEN** an evaluation in the queue is still non-terminal
- **THEN** the dashboard SHALL offer Cancel for it and SHALL NOT offer Clear

#### Scenario: Clear all terminal evaluations
- **WHEN** the user activates Clear all while one or more terminal evaluations are present
- **THEN** the dashboard SHALL clear all terminal evaluations and leave any non-terminal
  evaluations in the queue

#### Scenario: Clear all disabled when nothing is clearable
- **WHEN** the queue has no terminal evaluations
- **THEN** the dashboard SHALL disable the Clear all action
