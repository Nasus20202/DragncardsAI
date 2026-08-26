## Context

See `proposal.md`. `HistoryGamesList` renders all records returned by the
history-service, which partitions records by platform while allowing the same
game id in multiple partitions. Legacy records can omit `platform` and use the
DragnCards compatibility default.

## Goals / Non-Goals

**Goals:**

- Give every rendered History game row a stable key for its full history identity.
- Cover the cross-platform duplicate-id case without changing row behavior.

**Non-Goals:**

- Deduplicate history records or change history-service queries.
- Change selection, deletion, labels, test IDs, or API contracts.

## Decisions

### Use a normalized History identity value end-to-end

Introduce a small `HistoryGameRef` value containing a game id and normalized
platform (`platform ?? "dragncards"`). Store it for selection and delete targets,
then use it for list keys, active-state comparisons, API calls, deep links, and
reconstruction lifecycle checks. This matches the history-service partition and
gives legacy records the same compatibility identity used elsewhere in the
dashboard.

Alternatives considered:

- Use the map index — rejected because reorder or refresh would change component
  identity.
- Deduplicate by game id — rejected because it hides a valid platform record.
- Change the backend response — rejected because the backend already exposes the
  intended platform-partitioned model.

### Keep DragnCards compatibility defaults while making Marvel explicit

Existing `game_id` deep links and unqualified API calls remain DragnCards-compatible.
The workspace accepts an optional `platform` deep-link parameter; an unqualified
deep link prefers its DragnCards record and otherwise selects the matching record
that exists. Marvel list rows include the platform in requests where a service
needs it.

### Test the rendered duplicate-id case

Extend the closest History workspace test with two game records sharing an id
but carrying different platforms. Assert both rows render, can be independently
selected and deleted, and React reports no duplicate-key warning. Exercise the
platform-qualified deep-link and Marvel timeline/evaluation propagation.

Alternatives considered:

- Test only a key helper — rejected because React is the component that reports
  the regression.

## Risks / Trade-offs

- A future platform value could collide only if it is identical to another platform
  for the same game id → the history identity contract defines that pair as unique;
  the helper centralizes any future normalization change.
- Spying on console output can be sensitive to unrelated warnings → constrain the
  assertion to the duplicate-key message and restore the spy after the test.

## Migration Plan

Deploy as a dashboard-only change. No data migration or rollback procedure is
needed; reverting the single key expression restores prior behavior.
