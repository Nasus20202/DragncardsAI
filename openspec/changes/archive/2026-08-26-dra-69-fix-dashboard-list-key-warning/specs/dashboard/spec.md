## ADDED Requirements

### Requirement: Shared selectors render collision-safe option identities

The dashboard's shared `SelectField` and `ComboSelect` controls SHALL render at
most one option for each item value, retaining the first occurrence and its label
and order. Every rendered option SHALL have a unique React key and accessible DOM
identity, even when an upstream provider or model catalogue repeats a value.

The deduplication SHALL NOT change the value delivered when a user selects an
option, and SHALL NOT change filtering or the committed value shown by the
searchable control.

#### Scenario: Duplicate provider values render without a warning

- **WHEN** `SelectField` receives multiple items with the same value
- **THEN** it SHALL render one option for that value with no duplicate-key warning
- **AND** the rendered options SHALL have unique accessible identities

#### Scenario: Duplicate model values render without a warning

- **WHEN** `ComboSelect` receives multiple items with the same value
- **THEN** it SHALL render one option for that value with no duplicate-key warning
- **AND** the rendered options SHALL have unique accessible identities

#### Scenario: Selecting a deduplicated value preserves the selection contract

- **WHEN** a user selects an option whose value occurred more than once in the
  input catalogue
- **THEN** the control SHALL report that original value through `onChange`
