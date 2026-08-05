## ADDED Requirements

### Requirement: The Evaluate panel offers a selected skill's reference files

When a rules skill is selected for the judge in the Evaluate panel, the panel SHALL offer that skill's reference files as individually selectable entries, named as the catalogue reports them, and SHALL send the chosen references with the evaluation request.

A skill that is not selected SHALL NOT offer its references, and deselecting a skill SHALL drop any of its references that were selected, so a request never carries a reference for a skill the operator has turned off.

A skill with no reference files SHALL show no reference controls at all rather than an empty group.

#### Scenario: Selecting a skill reveals its references

- **WHEN** the operator selects a rules skill that has reference files in the Evaluate panel's judge configuration
- **THEN** that skill's reference files SHALL be shown as individually selectable entries

#### Scenario: Chosen references are sent with the request

- **WHEN** the operator selects one of a skill's reference files and starts an evaluation
- **THEN** the request's judge configuration SHALL name that reference

#### Scenario: Deselecting a skill drops its references

- **WHEN** the operator deselects a skill whose reference files were selected
- **THEN** those references SHALL no longer be selected and SHALL NOT be sent with the request
