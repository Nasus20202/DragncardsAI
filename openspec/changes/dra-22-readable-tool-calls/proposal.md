# Tool invocations read as invocations, not as JSON

## Why

A tool call is the most common thing in a Play transcript and the least readable.
Today each one produces two collapsed cards — "Tool call: move_card" and "Tool
result: move_card" — and opening either shows `JSON.stringify(payload, null, 2)`
of the whole event. The tool's name is buried in a label, its arguments are a
brace-and-quote block the reader has to parse by eye, and the answer sits in a
second card that has to be found and opened separately even though it is the
other half of the same thing. The reporter of DRA-22 put it plainly: *"The tool
invocations are not readable."*

The orchestration tools make this worse rather than better, because for them the
JSON is not even the interesting part:

- `spawn_subagent` returns `{"child_job_id": "…", "name": "…"}`. What the reader
  wants is not that string but the subagent — and the dashboard already has a
  view of a child job's transcript, reachable only from the floating subagent
  list in the corner, never from the call that started it.
- `wait_for_subagent` blocks. Its card is indistinguishable from a finished call
  nobody expanded, so the one moment when the transcript should say "the agent is
  stopped here, waiting" is the moment it says nothing at all.
- `load_skill` returns a whole `SKILL.md`. Its useful content is one word — the
  skill's name — and that word is the one thing the card does not show.

## What Changes

- **dashboard (event aggregation)** — a `tool_call` and the `tool_result` that
  answers it are aggregated into one `tool_exchange` item, paired by
  `tool_call_id` so parallel calls and interleaved events still pair correctly. A
  call with no result yet is what "still running" means, and an orphaned result
  is still shown rather than dropped.
- **dashboard (generic tool card)** — one card per invocation: the tool's name in
  monospace, a one-line summary of the arguments (`card_id: 01001a · to:
  player1Play`), and a state marker — a pulse while the call is out, an `error`
  chip when the result came back as one. Expanding lists each argument by name
  next to its value, then the result, then which server answered and which call
  it was.
- **dashboard (system tools)** — a registry maps a tool name to a presentation,
  so the tools whose shape is known get a card that says something better than
  "here are your arguments", and every tool absent from the registry — including
  every MCP tool nobody has thought about — gets the generic card:
  - `spawn_subagent` and `prompt_player_agent` name the child they started and
    carry a **View subagent** button that opens the existing subagent output
    view on that child job. `prompt_player_agent` also names the seat.
  - `wait_for_subagent` shows a live spinner and "waiting for <child>…" in its
    header, announced with `role="status"`, and turns into "collected <child>" —
    or "gave up on <child>" — once the wait ends.
  - `load_skill` and `load_skill_reference` put the skill and reference names on
    the header and the document behind the collapse, with its size as a hint.
- **dashboard (bounded rendering)** — every value a *collapsed* card shows comes
  from a bounded formatter that stops walking the payload once it has enough
  characters for the line. A collapsed card costs the same for a 400 kB board
  state as for a two-key call; an expanded one caps each argument and the result,
  with the rest one click away.
- **dashboard (redaction)** — every argument value and result string is redacted
  before display, using the same credential shapes
  `services/eval-service/src/eval_service/error_detail.py` redacts on the way
  into the evaluation store. Making a tool result *legible* also makes provider
  error bodies legible, and those carry keys.

## Why a registry rather than a chain of special cases

The bespoke set will grow — every new orchestration tool is a candidate — and it
will grow in a file that also holds the generic renderer. A `Record<name,
presentation>` plus a `Record<presentation, renderer>` keeps "which tools are
special" as one readable table, keeps the fallback in one place instead of at the
end of a widening conditional, and lets two tools share one presentation
(`spawn_subagent` and `prompt_player_agent` do). It also localises the thing this
change deliberately does not decide: if a richer component library is adopted
later, it is the renderers behind the table that change, not the transcript.

## On the issue's suggestion of OpenUI

The issue proposes "we can utilize OpenUI components". This change does **not**
add OpenUI or any other new UI dependency — that evaluation belongs to DRA-5,
which is deciding what OpenUI actually is and whether it ships anything to a
third party. Everything here is built from Hero UI (`Chip`, `Spinner`) and the
transcript's existing card styling, and nothing about the structure would have to
be redone to swap a richer component in: each presentation is one small renderer
behind the registry.

## Non-goals

- No new dependency, and no restyling of the transcript. The cards reuse the
  exact border, background, header and body classes the reasoning and compaction
  blocks already use, so a tool card looks like it always belonged there.
- No new subagent list view. The **View subagent** button opens the modal that
  exists today. DRA-21 owns improving that view, and this change deliberately
  links to what is there rather than pre-empting it.
- No change to the History tab's conversation transcript. It renders a captured
  OpenAI message array rather than orchestrator job events, so it has neither
  `tool_call_id` pairing nor an `is_error` flag to read; adopting these cards
  there is a separate, source-format-shaped piece of work.
- No windowing or virtualisation, consistent with DRA-8's measurement that the
  mounted node count is not the transcript's bottleneck.
- No server-side change. The orchestrator already records everything these cards
  need — `exposed_tool_name`, `arguments`, `tool_call_id`, `is_error`,
  `assignment` — so this is a rendering change only.
- No persisted per-card state. Which cards a reader has opened is view state in
  the component and is deliberately not stored anywhere.
