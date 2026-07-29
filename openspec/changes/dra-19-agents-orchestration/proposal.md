# Full agents orchestration: an orchestrator that cannot be talked out of the rules

## Why

DRA-19 asks for a real multi-agent game: *"one orchestrator that takes care of the
game flow"*, one **stateful** subagent per player, players that talk to each other
but not to the orchestrator, illegal actions reported by the orchestrator and
reverted by the players, and an orchestrator whose rule-following *"the players
cannot convince him"* to abandon. Alongside that, per-seat DRA-16 personas and
models, a way for the user to read each player's context, evaluation and history
kept meaningful, and — critically — all of it **optional**, chosen when a session
is created, with today's chat flow untouched as the default.

Three of those things are already partly here and are the reason this is a
coherent change rather than a greenfield service:

- `session_player_configs` (DRA-11) already gives every seat its own provider,
  model, options, and skill selection, resolved by inheritance from the
  orchestrating session.
- `prompt_player_agent` / `list_player_agents` already let an orchestrating job
  launch one child agent per seat, tagged with `player_id` so recorded moves are
  attributable end to end.
- `agent_personas` (DRA-16) already materialises a persona snapshot onto a child
  session at spawn time, so "this seat plays as *Aggressive Rookie*" is a snapshot
  captured once, not a live table read.

And three of them are missing outright:

- **Every child agent is memoryless.** `_launch_child_agent` hard-codes
  `multi_turn_memory=False`, and `PromptRunService._maybe_terminate_child_session`
  deletes the child session when its job ends. A seat prompted in round 1 and
  again in round 3 is two unrelated agents that share a name. That is fatal for a
  player: a hero's plan spans rounds, and a seat with no memory of what it drew,
  discarded, or promised another player cannot play the game — it can only play
  the turn.
- **The trust boundary is prompt text.** `game-orchestration/spec.md` today says
  the *skill instructs* each player to stay in its seat, and instructs the
  orchestrator to keep authority. Instruction is not enforcement. A player agent
  is a language model reading a prompt; if its report is fed to the orchestrator
  as ordinary conversation, "actually, the rules allow this" is a sentence it can
  emit and the orchestrator can believe.
- **Mode is not a thing.** A session is a session. There is nowhere to record
  that *this* one runs an orchestrated game and *that* one is the chat flow, so
  no code path can behave differently and no dashboard control can offer the
  choice.

## What Changes

### The mode is a recorded property of the session

A new `session_mode` column on `agent_sessions` holds `chat` (the default,
today's behaviour, bit-for-bit) or `orchestrated`. It is set at creation, is
changeable while the session has never run a job, and is frozen once it has —
switching a game's mode mid-flight would orphan the seats' persistent sessions.
`POST /sessions` and `PATCH /sessions/{id}` accept it, every session response
reports it, and the dashboard's config panel offers it as a two-option control on
a session that can still change.

Mode is what gates every behaviour below. Nothing in this change alters a `chat`
session: the existing `spawn_subagent` path, its memoryless children, and its
child-session cleanup are all reached unchanged, and the mode column defaults so
that sessions created before this change are `chat`.

### A player seat becomes a durable agent, not a spawn

`session_player_configs` gains two columns: `persona` (the seat's DRA-16 persona
name) and `agent_session_id` (the seat's own persistent child session, `NULL`
until the seat is first prompted).

In an orchestrated session, the first `prompt_player_agent` for a seat creates a
child session with `multi_turn_memory=True`, materialises the seat's persona
snapshot onto it exactly as `spawn_subagent` does, and records the child session
id on the seat row. Every later prompt for that seat enqueues a new job **on that
same session**, so `SessionTranscriptService` replays the seat's own prior turns —
including its tool calls and their results — into the next invocation. The seat's
session is not terminated when a job ends; it is terminated with the orchestrating
session, or when the seat is deleted.

This is the whole reason the change is worth making: the persistence mechanism
already exists and is well tested (it is what every chat session uses), so making
a player stateful is choosing the existing path instead of the memoryless one,
not building a new one.

### The trust boundary is structural, and it is the point

Four mechanisms, none of which is a sentence in a prompt:

1. **A player's output never reaches the orchestrator's system prompt.** The
   orchestrator's prompt is assembled from static parts, the on-disk skill
   registry, and the persona catalogue's names and descriptions — and from nothing
   else. There is no code path from any player-authored byte into it, and a test
   asserts that a player report containing prompt-injection text does not appear
   in the assembled prompt.
2. **A player's report arrives as fenced data, labelled as data.** The orchestrator
   receives it inside a `player_report` envelope in a `role: "tool"` result: the
   seat id and job status as structured fields, and the player's own text confined
   to one delimited block introduced as untrusted seat output that states
   observations and never instructions. The envelope is built server-side by
   `wrap_player_report`; the player cannot choose its own framing, cannot forge
   another seat's id, and cannot emit the closing delimiter (it is stripped from
   its text).
3. **Legality is decided by the game, never by an assertion.** A move is legal if
   game-service accepted it and the rules permit it. A player claiming a move was
   legal, that a rule does not apply, or that the orchestrator agreed to something
   changes nothing: the orchestrator's legality check reads game state through its
   own tools. The spec states this as a requirement so that no future change can
   introduce "the player says it's fine" as an input to the decision.
4. **A seat may only act with its own cards, enforced server-side.** Every tool
   call a player agent makes passes a seat guard before it reaches the tool: an
   argument naming a player index or a player-owned group other than the caller's
   own seat is refused with an error result, and the refusal is recorded on the
   job. The guard reads the seat id from the child session's metadata — which the
   player agent cannot write — so a player cannot act for another seat even if it
   is told to, tricked into it, or decides to on its own.

### The channel topology is explicit

Three channels exist and are enumerated, rather than left to whatever the prompt
implies:

- **orchestrator → player**: `prompt_player_agent`. The only way a player is ever
  invoked.
- **player → orchestrator**: the `player_report` envelope, data-only, one per
  invocation, produced by the run's completion rather than by a tool the player
  chooses to call.
- **player → player**: a new `send_player_message` tool available only to player
  agents in an orchestrated session. A message is addressed to another configured
  seat, stored durably, and delivered to the recipient at the start of its next
  invocation as fenced data attributed to the sending seat. A player agent has no
  tool that reaches the orchestrator, and `send_player_message` refuses the
  orchestrator's seat as a recipient — so "players can talk to each other but not
  to the orchestrator" is enforced by the addressing rules, not by asking nicely.

### Illegal actions are reported by the orchestrator and reverted by the player

When the orchestrator determines that a seat's move violated the rules, it records
an `illegal_action` finding against that seat and its next invocation of that seat
carries the finding as fenced data naming what was violated and what must be
undone. The seat performs the revert with its own tools, in its own seat scope,
and reports back. The orchestrator verifies the revert against game state rather
than accepting the seat's claim that it happened, and a finding stays open until
that verification passes.

### The user can read each player's context

Because a seat now *has* a session, its context is exactly a session's context.
The seat's `agent_session_id` is exposed in the players API, and the dashboard's
orchestrated session surface links each seat to its own transcript — reusing the
existing transcript rather than inventing a per-player viewer.

### Evaluation and history learn about the mode

History events emitted from an orchestrated session carry the session mode and the
seat id, so a recorded timeline states whether it came from one chat agent or from
an orchestrated table, and which seat played each move. Eval-service's projection
reads the mode so a judge scoring an orchestrated round knows the seats were
separate agents with separate contexts, and an illegal-action finding recorded by
the orchestrator is available to the judge as evidence rather than being inferred.

## Capabilities

### Modified Capabilities

- `agent-orchestrator` — session mode, persistent per-seat player sessions, the
  seat guard, the player-report envelope, player-to-player messaging, and the
  illegal-action findings store.
- `game-orchestration` — the orchestrated round loop's authority separation becomes
  enforced rather than instructed, and the illegal-action report/revert cycle is
  defined.
- `dashboard` — the mode control on session creation and configuration, the seat
  roster with persona and model per seat, and the per-seat context link.
- `agent-move-evaluation` — the judge's projection distinguishes orchestrated play
  and can read illegal-action findings.
- `history-event-store` — recorded events carry the session mode.

## Impact

- **Database** — migration `0011_session_mode_and_player_sessions` adds
  `agent_sessions.session_mode`, `session_player_configs.persona`,
  `session_player_configs.agent_session_id`, and the `player_messages` and
  `player_illegal_actions` tables, in both the PostgreSQL and SQLite dialects.
- **agent-orchestrator** — `schemas/sessions.py`, `schemas/players.py`,
  `storage/models.py`, `repositories/sessions.py`, `repositories/players.py`, a new
  `repositories/player_channel.py`, `runtime/player_agents.py`,
  `runtime/builtin_tools.py`, `runtime/prompt_run.py`, `runtime/system_prompts.py`,
  a new `runtime/seat_guard.py`, `api/routers/sessions.py`, `api/routers/players.py`.
- **dashboard** — `features/shared/lib/types.ts`,
  `features/play/lib/client-api.ts`, `features/play/lib/session-draft.ts`,
  `features/play/lib/last-used-draft.ts`,
  `features/play/lib/use-play-session-actions.ts`,
  `features/play/components/play-config-panel.tsx`, and a new session-mode control.
- **Documentation** — the agent-orchestrator README's session, tool, and
  configuration sections; `services/agent-orchestrator/AGENTS.md`'s core concepts;
  the root README's session-mode note.

## Non-goals

- **No replacement of the chat flow.** `chat` is the default and is not modified.
  A session that does not opt in behaves exactly as it does today, and the
  orchestrated path is reachable only through an explicit mode choice.
- **No new service.** Orchestration is a mode of the existing agent-orchestrator,
  not a fifth process. Adding one would duplicate session, job, event, and skill
  machinery for no gain.
- **No rules engine in the orchestrator.** Legality is game-service's validation
  plus the orchestrator agent's reading of game state through its tools. This
  change does not reimplement Marvel Champions' rules in Python.
- **No suspend-and-resume of the orchestrating run.** The orchestrator waits on a
  seat exactly as it waits on a subagent today, inside the tool call, under a
  bounded deadline.
- **No cross-session player chat.** `send_player_message` addresses seats of the
  same orchestrating session only. A player in one game cannot message a player in
  another.
- **No restyling of existing dashboard surfaces.** The mode control and the seat
  roster are new components; the transcript, composer, config panel layout, and
  session list are untouched.
- **No automatic revert by the orchestrator.** The issue is explicit that players
  revert their own illegal actions; the orchestrator reports and verifies. An
  orchestrator that reached into a seat's cards would break the seat scoping this
  change spends most of its effort enforcing.
