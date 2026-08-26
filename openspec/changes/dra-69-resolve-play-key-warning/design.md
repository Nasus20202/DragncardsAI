## Context

The Play transcript receives durable job events and live stream updates. Before
rendering, `aggregateEvents` folds adjacent reasoning and model-output chunks,
pairs tool calls with results, and emits one row for each visible event unit. Both
the main transcript and the subagent output modal currently key those rows by
their array index. A row's index is only its current position and can change when
the event list is replayed, filtered, or extended.

The earlier DRA-69 implementation deduplicated repeated provider and model
selector values. That fix is retained. This change addresses the separate event
row render path that remained capable of producing the reported development
warning and of transferring state between rows after an insertion.

## Goals / Non-goals

**Goals:**

- Give every aggregated row a stable identity derived from its source event.
- Keep the identity of coalesced reasoning and model-output rows anchored to the
  first event that contributed their visible text.
- Use one identity contract in the main transcript and the subagent output view.
- Prove that distinct source events with identical visible content have distinct
  identities and do not emit a React key warning.

**Non-goals:**

- Changing which events are folded, paired, omitted, or displayed.
- Using model text, tool-call arguments, or other mutable payload content as a
  React key.
- Modifying shared selector components, selector identities, history views, or
  any service outside the dashboard Play feature.

## Decisions

### Carry identity through aggregation

`AggEvent` gains a `key` field. Event-backed rows use the source event type and
event ID. A reasoning or model-output row records the first source event before
later chunks are appended. When completion text is the first visible text for a
row, the completion event supplies its identity; when streamed text already
exists, the existing stream event identity remains in place.

Alternative considered: compute a key in each component from the rendered
`AggEvent`. Rejected because text-only rows no longer expose the source event
that created them, which would force mutable content or positions into the key
and make the two views diverge.

### Share the aggregated key in both Play views

`PlayTranscript` and `SubagentOutputModal` both consume `aggregateEvents`, so
both use `agg.key`. This keeps row identity behavior identical for a parent job
and a child job without duplicating key derivation logic.

Alternative considered: give only the main transcript stable keys. Rejected
because the subagent modal renders the same row kinds and can receive the same
stream/replay transitions.

### Keep source IDs separate from visible content

The key combines the source event type and ID rather than using text, event kind
alone, or the tool-call ID. Event IDs remain stable when a stream snapshot's
payload changes, and the type prefix keeps different event categories distinct
without exposing payload data to React identity logic.

## Risks / Trade-offs

- Aggregated rows intentionally keep the first contributing event's identity, so
  a completed response that replaces a partial stream keeps the partial row's
  component state. This matches the fact that it is one visible response row.
- The event ID is assumed to be the durable identity already used by the stream
  upsert logic. Invalid duplicate IDs from an upstream response remain an input
  data problem rather than a new selection or persistence behavior.
- The change adds a field to the internal `AggEvent` union, but does not alter
  the event API or persisted event shape.

## Verification

Run the focused Play transcript Vitest files covering aggregation, the transcript
render path, tool exchanges, user questions, OpenUI question rendering, and
memoisation. Run the dashboard TypeScript check. The parent orchestrator owns
the broader repository validation and any browser verification.
