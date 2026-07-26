## ADDED Requirements

### Requirement: History-driven game picker with delete

The dashboard history view SHALL source its game picker from games-with-recorded-history and SHALL provide a control to delete all history for the selected game, with a confirmation step, refreshing the picker and clearing the selection after a successful deletion.

#### Scenario: Picking a recorded game

- WHEN the user opens the history view
- THEN the game picker lists games that have recorded history and selecting one loads its timeline

#### Scenario: Deleting a game's history

- WHEN the user deletes the selected game's history and confirms
- THEN the dashboard calls the delete endpoint, clears the selection, and refreshes the game list so the deleted game no longer appears

### Requirement: Play-parity judge configuration in the evaluate control

The dashboard Evaluate control SHALL let the user configure the judge per evaluation — provider and model, reasoning effort, a custom prompt/rubric, and selected rules skills — reusing the same provider and skill sources as the Play flow, and SHALL include the chosen configuration in the evaluation request, omitting empty fields.

#### Scenario: Configuring and submitting a judge

- WHEN the user selects a provider/model, sets reasoning, optionally edits the prompt, picks skills, and submits an evaluation
- THEN the request carries the chosen judge configuration and the resulting verdict reflects the selected model

### Requirement: Live evaluation status with cancel

The dashboard Evaluate control SHALL display live per-target evaluation status and incremental judge output via the eval-service stream, SHALL provide a Cancel control while the request is in flight, and SHALL refresh the timeline when the request completes so new evaluator events appear.

#### Scenario: Watching and cancelling an evaluation

- WHEN an evaluation is running
- THEN the control shows live per-target status and streamed judge output, offers a Cancel control that stops the in-flight evaluation, and on completion refreshes the timeline to show the new evaluator events
