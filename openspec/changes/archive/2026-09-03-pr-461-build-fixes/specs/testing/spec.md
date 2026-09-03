## MODIFIED Requirements

### Requirement: DragnCards plugin artifacts remain engine-compatible

The integration suite SHALL validate that the checked-in DragnCards plugin artifacts contain only executable DragnLang variable definitions before exercising live plugin workflows.

#### Scenario: Plugin automation variables have valid names
- **WHEN** the integration suite loads the Marvel Champions plugin automation artifact
- **THEN** every `VAR` operation SHALL define a non-empty variable name beginning with `$`
