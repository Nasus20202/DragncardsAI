## ADDED Requirements

### Requirement: Play event rows use stable source identities

The dashboard's `PlayTranscript` and `SubagentOutputModal` SHALL key each
aggregated event row with an identity derived from its source job event rather
than its current array position or mutable rendered content. The aggregation
SHALL retain the first contributing source identity when it combines reasoning
or model-output events into one row. Distinct source events SHALL receive
distinct row identities even when they have the same event type or visible text.

#### Scenario: Same-content event rows remain distinct

- **WHEN** a job contains two visible event rows with identical rendered text
  but different source event IDs
- **THEN** the Play transcript SHALL render both rows without a duplicate-key
  warning
- **AND** each row SHALL retain its own source-derived identity

#### Scenario: A later event does not change earlier row identities

- **WHEN** a later event is appended to a job after the transcript has rendered
  existing rows
- **THEN** the existing rows SHALL keep their source-derived identities
- **AND** React component state SHALL remain associated with the same event row

#### Scenario: Subagent output uses the same identity contract

- **WHEN** the subagent output modal renders aggregated events from a child job
- **THEN** each rendered row SHALL use the same source-event identity rule as the
  main Play transcript
