## ADDED Requirements

### Requirement: The judge knows whether it is scoring orchestrated play
The projection a judge is given SHALL state the orchestration mode of the play it is scoring. When the mode is orchestrated, the projection SHALL state that each seat was a separate agent holding its own context and its own persona, so the judge does not penalise a seat for failing to account for information it could not have seen.

When the mode is chat the projection SHALL read as it does today, so existing verdicts remain comparable.

#### Scenario: An orchestrated round is projected as orchestrated
- **WHEN** a round from an orchestrated session is projected for the judge
- **THEN** the projection SHALL state the orchestrated mode and that each seat held its own separate context

#### Scenario: A chat round is projected unchanged
- **WHEN** a round from a chat session is projected for the judge
- **THEN** the projection SHALL be the one produced before orchestrated mode existed

### Requirement: Illegal-action findings are evidence available to the judge
When the orchestrator has recorded that a seat's action violated the rules, that finding SHALL be available to the judge as recorded evidence for the round it belongs to, naming the seat, the violation, and whether it was resolved. The judge SHALL NOT have to infer a rules violation from the move list when the orchestrator already recorded one.

A finding SHALL be evidence and SHALL NOT by itself determine a verdict: the judge weighs it alongside everything else in the projection.

#### Scenario: A recorded violation reaches the judge
- **WHEN** a round contains a seat action the orchestrator recorded as illegal
- **THEN** the projection for that round SHALL include the finding naming the seat, the violation, and its resolution state

#### Scenario: A resolved violation is distinguishable from an open one
- **WHEN** a round's finding was resolved after the seat undid the action
- **THEN** the projection SHALL show it as resolved rather than open
