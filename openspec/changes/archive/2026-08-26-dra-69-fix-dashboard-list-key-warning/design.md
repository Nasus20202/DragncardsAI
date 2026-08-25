## Context

The shared dashboard selectors receive arrays assembled from provider and model
catalogues. Those arrays can contain the same value more than once. React keys and
option IDs are currently derived directly from that value, so the initial Play
settings render can report duplicate children before any user action occurs.

## Goals / Non-Goals

**Goals:**

- Ensure each selector renders at most one option for a value.
- Preserve the first occurrence's label, order, value, and accessible identity.
- Cover both the plain select and searchable combo select with a focused regression.

**Non-Goals:**

- Normalising or mutating catalogues outside the shared selector render boundary.
- Creating synthetic values that could alter selection callbacks.
- Changing the component's filtering or committed-value behavior.

## Decisions

### Deduplicate at the shared render boundary

The selectors will filter repeated values before mapping options. The first item is
retained, so existing values remain the values sent through `onChange`, and an
upstream duplicate cannot create a second selectable row for the same value.

Alternative considered: generate an index-suffixed React key only. Rejected because
the option `id` would still collide and the duplicate value would remain ambiguous
to assistive technology. Alternative considered: deduplicate each provider/model
catalogue at every caller. Rejected because other dashboard panels use the same
shared controls and callers should not need to know the controls' identity
constraint.

### Reuse one value-deduplication helper

The plain select and combo select will share a small generic helper based on a
`Set`, preserving input order and the first item for each string value. This keeps
the two rendering paths aligned without changing their public item types.

Alternative considered: duplicate the filtering expression in each component.
Rejected because the two controls could drift and reintroduce different duplicate
handling. Alternative considered: change the item type to require a separate key.
Rejected because callers already use the value as the stable selection contract and
the fix does not require an API change.

## Risks / Trade-offs

- If an upstream catalogue repeats a value with different labels, only the first
  label remains visible; the value cannot distinguish those entries, so retaining
  the first occurrence is deterministic and preserves the existing selection
  contract.
- Deduplication occurs during rendering and does not repair the upstream response;
  future consumers that render catalogues directly remain responsible for their own
  option identity.
- No DragnCards, WebSocket, or external-upstream protocol behavior is involved.

## Verification

Run the shared selector Vitest file and the dashboard TypeScript and ESLint checks.
If the local dashboard and its backing services are available, open `/play` in a
browser with console warnings captured and confirm the initial settings render is
quiet. A browser check is supplementary to the deterministic regression test.

The local dashboard was reachable and was also started from this worktree on port
3101 for a browser probe. The probe still observed React key warnings from other
render paths on `/play`, so global console silence could not be confirmed within
this change's allowed shared-selector scope. The focused duplicate-value test and
the selector behavior remain warning-free.
