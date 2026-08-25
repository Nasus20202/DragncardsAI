# Tasks

## 1. Shared selector fix and regression coverage

- [x] 1.1 Add value-based deduplication for rendered options in `ComboSelect` and `SelectField`, preserving first-item order and selection values.
- [x] 1.2 Add focused Vitest coverage for duplicate values, React warning suppression, and unique rendered option IDs in both shared selectors.

## 2. Validate and complete the specification

- [x] 2.1 Run focused dashboard Vitest coverage and the dashboard lint and typecheck commands.
- [x] 2.2 Attempt browser verification of the initial `/play` render and record whether the local stack was available.
- [x] 2.3 Archive this change so the dashboard main spec reflects the shipped duplicate-option identity behavior.
