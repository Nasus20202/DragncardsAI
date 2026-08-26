# Resolve unstable keys in the Play transcript

## User report

> ## Error Type
>
> Console Error
>
> ## Error Message
>
> Each child in a list should have a unique "key" prop.
>
> Check the render method of `no`. It was passed a child from ed. See [https://react.dev/link/warning-keys](https://react.dev/link/warning-keys) for more information.
>
> ```
> at div (unknown:0:0)
> ```
>
> Next.js version: 16.3.3 (Turbopack)

## Interpretation

The warning is emitted by a remaining `/play` render path rather than by the
provider/model selector catalogue. The Play transcript and the subagent output
view both render aggregated event rows with their array position as the React
key. Those positions are not identities: aggregation can insert, remove, or
replace rows as event history is replayed and streamed. The prior selector
deduplication from commit `161892d` remains part of the dashboard behavior and is
not changed here.

## Why

`aggregateEvents` combines adjacent reasoning and model-output events and pairs
tool calls with their results. A positional key therefore changes when a row is
inserted before it, while a content-derived key can collide when two rows contain
the same text. The two Play render paths need the same event-derived identity so
stream updates preserve the intended row and React never receives duplicate row
keys for distinct source events.

## What changes

- Attach a stable source-event key to every aggregated Play event row.
- Preserve the first contributing event identity for coalesced reasoning and
  model-output rows, including completion text that replaces streamed text.
- Use those identities in both `PlayTranscript` and `SubagentOutputModal` instead
  of array positions.
- Add focused dashboard regression coverage for distinct same-content rows,
  stable identities after later events arrive, and duplicate-key warning absence.

## Modified capabilities

- `dashboard` — Play transcript and subagent output rows retain stable React
  identities while event streams are aggregated and updated.

## Impact

- Dashboard Play event aggregation and the two views that render its rows.
- Focused dashboard Vitest coverage only.
- No API, persistence, history-service, selector, or shared-selector changes.

## Non-goals

- Changing event ordering, aggregation semantics, or the content shown by a row.
- Changing provider/model selector behavior delivered by the earlier DRA-69 fix.
- Reworking unrelated dashboard lists or adding browser automation coverage.
