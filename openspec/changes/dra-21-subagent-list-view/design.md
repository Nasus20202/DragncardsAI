# Design

## Decision: two halves to a name — a hashed codename and a mined topic

A name has to do two different jobs and one string cannot do them by accident.
"Told apart at a glance" wants maximum difference between siblings; "says what it
does" wants fidelity to the prompt. The prompts of a run of subagents are highly
similar by construction, so fidelity alone produces near-identical labels — which
is precisely today's bug. Splitting the name gives each job its own half:
`Amber Comet · search cards marvel champions`.

The codename is `blake2b(seed)` indexed into 32 adjectives and 32 animals — 1024
pairs, which is far more than the number of subagents any one session spawns, and
the pair is a pure function of the seed.

The topic is mined from the prompt: split into atoms, discard the atoms that are
not words, drop function words and the orchestrator's own instruction boilerplate,
deduplicate, and take up to five words within a 44-character budget.

**Alternatives considered.**

- *Ask a model for a name.* Rejected: a name would cost a token and a round trip
  at the exact moment the parent agent is trying not to block, it would vary
  between two runs on the same prompt, and a naming call can fail while the spawn
  it names must not.
- *A topic alone, better extracted.* Rejected: no extraction rescues six prompts
  that genuinely start with the same sentence. This was the first thing tried and
  it is what the codename exists to fix.
- *A codename alone.* Rejected: it makes the entries distinguishable and
  meaningless, which answers half the issue and loses the half the reader
  actually needs when choosing which subagent to open.
- *A monotonic ordinal (`Subagent 3`).* Rejected: it needs a per-parent counter
  that is a query or a shared counter, it says nothing about the work, and it is
  ambiguous the moment two parent jobs are open in one session.

## Decision: the seed is the child session's own id, so the row is created first

The codename must be unique per subagent, and the only thing guaranteed unique at
spawn time is the id of a row that does not exist yet. So `_launch_child_agent`
creates the child session unnamed, generates the name from `child_session.id` and
the prompt, and writes it back with one `UPDATE`. The name then flows into the
`subagent_started` payload, the monitor's outcome events and the tool result from
that single generation.

**Alternatives considered.**

- *Seed on the parent `job_id` plus the prompt.* Rejected: it needs no extra
  write, but two spawns with the same prompt under one parent — a retry, or a
  deliberate pair of identical probes — would collide, and colliding names are
  the bug this change is fixing.
- *Seed on a fresh random token.* Rejected: it removes the extra write and is
  unique, but the name stops being reproducible from anything stored, so nothing
  can ever verify that a stored name is the name that record should have.
- *Add an id parameter to `create_session`.* Rejected: it puts primary-key
  generation in the caller to save one small `UPDATE` on a path that already
  performs several writes per spawn.

## Decision: an atom is rejected whole, and only word-shaped atoms are mined

The topic extractor splits on everything that is not a letter, digit or
underscore, and accepts an atom only if every underscore-separated part of it is
alphabetic *and* is all lower case, all upper case, or capitalised.

That single rule does three things at once. It keeps `search_cards_marvel_champions`
(four lower-case words) and `Spider`/`Man` (capitalised). It discards
`player1Play`, `01001a` and a UUID, which are identifiers and say nothing. And it
discards the mixed-case letter runs that credentials and base64 are made of, so a
prompt that happens to carry a key cannot donate an eight-letter fragment of it to
a name that is then stored and displayed.

**Alternatives considered.**

- *Split on letters only and cap word length.* Rejected: that was the first
  implementation, and it mines `AbCdEfGh` out of `sk-proj-AbCdEfGh12` because the
  digits are dropped before the letters are judged.
- *Run the orchestrator's redaction patterns over the prompt first.* Rejected as
  the primary mechanism: those patterns match a credential by the field name in
  front of it, and a topic is built from bare words with their context already
  discarded. The word-shape rule is the one that survives losing the context.

## Decision: the dashboard stops deriving names, and the endpoint does it

Naming an unnamed session from its first prompt moves into
`POST /sessions/{id}/prompts`. The endpoint reads the session and its job count
before enqueuing, so "first prompt" is decided without counting the job it is
about to add, and renames only when the session has no name and no prior job.

The dashboard change that makes this reachable is that a new session's draft
starts unnamed rather than holding a timestamp — otherwise the server's
"has no name" condition would never be true. `saveConfiguration` sends `null`
rather than inventing a name, so saving settings on a fresh session does not
consume its chance to be named.

**Alternatives considered.**

- *Keep naming in the dashboard, just generate better names.* Rejected: two
  browsers on one session would each derive their own name, and the repository
  requires a generated name that must be stable across reloads to live in
  PostgreSQL rather than be recomputed per client.
- *Rename on the first prompt regardless of the current name.* Rejected: that is
  what the dashboard did, and it silently overwrites a name an API client or a
  user chose deliberately.
- *Name the session in the worker when the job starts.* Rejected: the name would
  appear some seconds after the prompt, so the sidebar would show the old label
  during exactly the period the user is watching it.

## Decision: bound the box, do not bound the panel

The height cap and `overflow-y-auto` go on the element that holds the entries,
inside the component, not on the absolutely positioned wrapper in
`play-workspace.tsx`. The header and the filter stay outside the scroll area, so
they do not scroll away from the list they control, and the component is
self-contained: it is correct wherever it is mounted rather than correct because
of a class on its parent.

`overscroll-contain` is on the box because it floats over the transcript, and a
wheel gesture that reaches the end of the list must not continue into the
transcript underneath it.

**Alternatives considered.**

- *Cap the wrapper in `play-workspace.tsx`.* Rejected: it works only for this one
  mount point and leaves the component able to overflow anywhere else.
- *Windowing / virtualisation.* Rejected: a session spawns tens of subagents. The
  cost being fixed here is a layout bug, not a render-count bug.
- *Cap the number of entries rendered and hide the rest.* Rejected: it is a fix
  that loses information, and the entries beyond the cap were exactly the ones the
  reporter could not reach.

## Decision: the filter appears only when the list is expanded

Collapsed, the list shows the running and the failed and nothing else, which is
the at-a-glance state and is what it already did. Expanded, the filter appears and
governs what is shown, defaulting to All. Two mechanisms coexist without
overlapping: the toggle decides *whether* you are looking at the whole list, the
filter decides *which part* of it.

The control is Hero UI's `ToggleButtonGroup` with `selectionMode="single"` and
`disallowEmptySelection`, which gives keyboard navigation and single-selection
semantics for free, sized down with `h-6 px-2 text-[10px]` so it matches the 10px
chrome around it. Each button carries its count, so the reader knows what a filter
will show before choosing it, and a status with nothing in it renders an explicit
note rather than an empty box.

**Alternatives considered.**

- *A `Select` dropdown.* Rejected: four options behind a click, in a panel whose
  whole purpose is to be readable without interaction.
- *A hand-rolled row of buttons.* Rejected: the surrounding list is hand-rolled,
  but this is a new control with selection semantics, and the repository's
  guidance is that a genuinely new sub-control comes from Hero UI.
- *Multi-select statuses.* Rejected: with three statuses, single selection plus
  All covers every useful combination but one.

## Risks

- The `subagent_started` payloads and session names already stored keep their old
  `prompt[:50]` values, so a session opened from history shows old-style names
  beside new-style ones. Accepted deliberately: a backfill would rewrite labels
  users have already read. The mitigation that matters is redaction, since those
  old names are raw model-written text.
- `POST /sessions/{id}/prompts` gains one `SELECT` for the session and one for the
  job count on every prompt, plus one `UPDATE` on the first. Both reads are by
  primary key or by an indexed `session_id` with `limit=1`.
- A caller that creates a session with `name: ""` now gets a generated name where
  before it got an empty one. That is the intended behaviour and is what the
  dashboard relies on.
