## ADDED Requirements

### Requirement: The skill catalogue reports each skill's reference files

The agent-orchestrator's skill catalogue SHALL report, for each discovered skill, the relative paths of that skill's markdown reference files. A skill with no reference files SHALL report an empty list rather than omitting the field, so a consumer never has to distinguish "no references" from "not reported".

The reported paths SHALL be exactly the names the skill's reference loader accepts, so a consumer can offer a listed reference for selection and have that selection resolve.

#### Scenario: A skill with references lists them

- **WHEN** the skill catalogue is read for a skill that has markdown files beside its `SKILL.md`
- **THEN** the catalogue entry SHALL list each of those files by its path relative to the skill directory

#### Scenario: A skill without references reports an empty list

- **WHEN** the skill catalogue is read for a skill whose directory holds only `SKILL.md`
- **THEN** the catalogue entry SHALL report an empty reference list
