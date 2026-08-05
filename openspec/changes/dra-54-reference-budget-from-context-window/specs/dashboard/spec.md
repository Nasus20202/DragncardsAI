## MODIFIED Requirements

### Requirement: The Evaluate panel offers a selected skill's reference files

When a rules skill is selected for the judge in the Evaluate panel, the panel SHALL offer that skill's reference files as individually selectable entries, named as the catalogue reports them, and SHALL send the chosen references with the evaluation request.

A skill that is not selected SHALL NOT offer its references, and deselecting a skill SHALL drop any of its references that were selected, so a request never carries a reference for a skill the operator has turned off.

A skill with no reference files SHALL show no reference controls at all rather than an empty group.

The panel SHALL offer a control that selects EVERY reference of every selected skill in one action, and a control that clears them all. Each skill's group SHALL additionally offer the same pair scoped to that skill alone. The panel SHALL NOT cap how many references may be selected, and SHALL NOT disable an unselected reference on account of how many are already selected; the size budget is the server's to enforce and its refusal explains itself.

#### Scenario: Selecting a skill reveals its references

- **WHEN** the operator selects a rules skill that has reference files in the Evaluate panel's judge configuration
- **THEN** that skill's reference files SHALL be shown as individually selectable entries

#### Scenario: Chosen references are sent with the request

- **WHEN** the operator selects one of a skill's reference files and starts an evaluation
- **THEN** the request's judge configuration SHALL name that reference

#### Scenario: Deselecting a skill drops its references

- **WHEN** the operator deselects a skill whose reference files were selected
- **THEN** those references SHALL no longer be selected and SHALL NOT be sent with the request

#### Scenario: Select all takes every reference of every selected skill

- **WHEN** the operator activates the panel's select-all reference control
- **THEN** every reference file of every selected skill SHALL become selected

#### Scenario: A skill group selects and clears its own references

- **WHEN** the operator activates a skill group's select-all or clear control
- **THEN** only that skill's reference files SHALL change selection, and other skills' selections SHALL be left as they were

#### Scenario: No reference is blocked by how many are already selected

- **WHEN** the operator has selected any number of reference files
- **THEN** every remaining reference file SHALL stay selectable
