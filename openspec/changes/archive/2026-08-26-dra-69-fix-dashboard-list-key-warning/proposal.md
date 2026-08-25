# Prevent duplicate option keys in dashboard selectors

## User report

> "React key warning appears immediately on `/play`."

## Why

The Play settings panel can initially receive repeated provider or model values.
The shared `SelectField` and `ComboSelect` render each item with its value as both
the React key and option identity, so a repeated value produces a React warning and
duplicate accessible option identities before the user interacts with the page.

## What changes

- Deduplicate rendered options by value in both shared selector components, keeping
  the first item and its existing selection value and identity.
- Add a regression test covering duplicate values, warning-free rendering, and
  unique rendered option IDs for both selectors.

## Capabilities

### Modified Capabilities

- `dashboard` — shared provider/model selectors render duplicate upstream values
  without key warnings or duplicate accessible option identities.

## Impact

- Dashboard shared selector components and their focused Vitest coverage.
- No API, persistence, provider, infrastructure, or other service changes.

## Non-goals

- Changing provider/model catalog data or selection semantics.
- Changing selector styling, labels, filtering behavior, or dashboard layout.
- Adding a browser automation suite or changing unrelated Play workspace behavior.
