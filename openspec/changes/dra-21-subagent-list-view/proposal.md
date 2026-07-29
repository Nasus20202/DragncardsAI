# The subagent list stays on screen, and the things in it have names

## Why

The Play workspace lists a session's subagents in a floating panel in the top
right corner of the transcript. DRA-21 reports four things wrong with it, and
they compound:

- **It overflows.** The panel has no height. Expanding it with a dozen finished
  subagents produces a column taller than the viewport, and because the panel is
  absolutely positioned there is nothing to push — the entries past the fold are
  simply off screen.
- **It does not scroll.** Neither the panel nor anything containing it scrolls, so
  those entries are not merely below the fold, they are unreachable.
- **The names are not meaningful.** A subagent's name is `prompt[:50]`. Every
  orchestrator prompt opens with the same instruction boilerplate ("You are a
  subagent. The session id is …"), so a run of six subagents renders as six
  entries reading *"You are a subagent. The session id is 7f3a91c4-2b1"*. A
  session's name has the same problem from the other end: it starts as a
  timestamp, which distinguishes two sessions only by the minute they were
  created in, and is then overwritten by the dashboard with the first sixty
  characters of the first prompt.
- **There is no filter.** The one thing the reporter wants to do — stop looking at
  the finished ones — is the thing the panel cannot do.

## What Changes

- **agent-orchestrator (name generation)** — a new `runtime/display_names.py`
  produces a name in two halves: a **codename** (one adjective and one animal,
  chosen by hashing a seed) whose job is to be told apart at a glance, and a
  **topic** (a few content words lifted from the prompt) whose job is to say what
  the agent was asked to do. `Amber Comet · search cards marvel champions`.
  Both halves are pure functions of their inputs, so a name costs no model call
  and cannot vary between two renders of the same record.
- **agent-orchestrator (subagents)** — `spawn_subagent` no longer names its child
  from the prompt. The child session is created unnamed and then named from its
  own session id, which is what makes each codename unique, and the generated name
  is stored on the child session and copied into the `subagent_started` event and
  the tool result. `prompt_player_agent` is untouched: a seat's hero name is
  already meaningful, and a caller that supplies a name still wins.
- **agent-orchestrator (sessions)** — `POST /sessions/{id}/prompts` names a session
  that has no name and no prior job, from that first prompt, inside the same
  request. A session whose creator gave it a name is never renamed, and a session
  that has already run is never renamed.
- **dashboard (naming)** — the dashboard stops deriving names. A new session's
  draft starts unnamed instead of holding a timestamp, and the
  `PATCH /sessions/{id}` that used to set `prompt.slice(0, 60)` after the first
  prompt is gone. Refreshing the session list is enough to show what the server
  generated.
- **dashboard (the list)** — the entries live in a box with a height cap
  (`max-h-[min(45vh,16rem)]`) and its own `overflow-y-auto`, so a long list
  scrolls inside itself and the page never grows to fit it. Each entry carries the
  full name as a `title` because a generated name is longer than the row.
- **dashboard (the filter)** — expanding the list reveals a status filter — All,
  Live, Done, Failed, each labelled with its count — built from Hero UI's
  `ToggleButtonGroup` and sized down to the list's own 10px chrome. Collapsed, the
  list still shows exactly what it showed before: the running and the failed.
- **dashboard (redaction)** — the name and failure reason a list entry displays,
  and the name in the subagent output modal's header, go through the same
  `redactSecrets` the tool cards use. This is not about the generated names, which
  cannot carry a credential; it is about the names already stored from before this
  change, which are raw slices of model-written prompts and are replayed from
  storage for as long as the session exists.

## Why the name is generated on the server and stored

A generated name has to be the same name in every browser looking at the session,
and the same name tomorrow. Deriving it in the dashboard fails both: two clients
render two different names for one subagent, and a name computed at render time
is a name that changes when the derivation changes. Generating it once, on the
server, and writing it to `agent_sessions.name` and into the event payload means
every reader afterwards reads one stored string. This is also why the child
session is created unnamed and then named: the seed that makes the codename unique
is the child's own id, and that does not exist until the row does.

No migration is needed. `agent_sessions.name` already exists and
`job_events.payload` is free-form JSON; what changed is what gets written into
them.

## Why status is the filter axis

The complaint is specifically that *finished* subagents crowd the list. Status is
the axis that answers it, it is already on every entry with no extra fetch, and
it is the axis the collapsed view was informally filtering on all along.
Filtering by persona or by age was considered and rejected: neither is what the
reporter asked for, persona is set on only some subagents, and both would need the
list to carry data it does not have today.

## Non-goals

- **No re-theming.** This is an existing component. The header, the entry rows,
  the status marks and the failure tooltip keep the exact classes they had. The
  filter is the one new control, and it is sized to the list rather than the list
  being resized to it.
- **No new subagent view.** DRA-22's **View subagent** button still opens the same
  `SubagentOutputModal` on the same child job, and the name it passes is now the
  generated one for free, because it reads the name out of the tool result the
  orchestrator writes.
- **No persisted filter.** Which status the reader is looking at is view state in
  the component and is deliberately stored nowhere.
- **No windowing.** The height cap plus native scrolling is the whole fix; a
  subagent list is tens of entries, not thousands.
- **No change to how a subagent runs.** Nothing about configuration inheritance,
  persona capture, monitoring or termination is touched — only what the child is
  called.
- **No renaming of existing rows.** Sessions and subagents named before this
  change keep the names they have; a backfill would rewrite history that users
  have already read, and the redaction above is what makes those old names safe to
  keep displaying.
