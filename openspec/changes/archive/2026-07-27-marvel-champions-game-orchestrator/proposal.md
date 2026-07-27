# Marvel Champions game orchestrator with per-player agent configurations

## Why

Today a single agent session drives an entire Marvel Champions game. That makes
it impossible to answer the question the eval pipeline exists to answer: *how
well does this configuration play a hero?* One agent takes every decision for
every seat, so a verdict grades a blend of roles rather than a player.

Marvel Champions is cooperative: one to four players each control their own
hero and play together against a villain and encounter deck that the game rules
run. Modelling that faithfully means one agent per seat, each acting only on its
own turn and only with its own hero, plus a coordinator that runs the parts of
the round that belong to nobody — phase transitions, the villain phase, the
first-player marker, win/loss detection.

Once seats are separate agents, each seat can carry its **own** provider, model,
reasoning effort, and skill list. Two configurations can then sit at the same
table, play the same scenario, and be compared move-for-move by the existing
eval-service, which already attributes, judges, and reports **per player**.

The pieces that block this today:

- Nothing lets a user express "player1 uses this model and these skills,
  player2 uses those". Session config is a single flat model config plus one
  skill set.
- `spawn_subagent` copies the parent's config verbatim; a child cannot be given
  a different provider, model, reasoning, or skill list.
- Agent moves reach the history timeline with no acting-player identity, so
  eval-service must *guess* the seat from `firstPlayer` rotation. With real
  per-seat agents the truth is known at emission time and should be recorded.

## What Changes

- **skills** — add a `marvel-champions-orchestrator` skill: the round-by-round
  playbook an orchestrator session follows to run a full cooperative game
  (setup, player phase turn-by-turn prompting, end-of-player-phase, villain
  phase, first-player pass, win/loss detection, round logging), plus references
  for the round loop and the per-turn prompt contract.
- **agent-orchestrator (storage + API)** — add a `session_player_configs` table
  and a `/sessions/{id}/players` API so each seat (`player1`..`player4`) gets an
  independently configured provider, model, reasoning effort, skill list, and
  raw gateway/provider option overrides. Unset fields inherit the orchestrator
  session's own configuration.
- **agent-orchestrator (runtime)** — add two master-job built-in tools,
  `list_player_agents` and `prompt_player_agent`, registered only for sessions
  that have a player roster. `prompt_player_agent` spawns a child session
  configured from that seat's stored config (not the parent's), tags it with the
  seat id and the orchestrator's `game_id`, and reuses the existing subagent
  scheduling, monitoring, and `wait_for_subagent` machinery.
- **agent-orchestrator (history)** — agent-move envelopes emitted from a player
  session carry the acting seat as `payload.player`.
- **eval-service** — prefer an explicitly recorded `payload.player` over the
  `firstPlayer`-rotation heuristic when attributing a move.
- **dashboard** — add the client-side plumbing (types, draft assembly, API
  wrappers) for a per-player roster. The visual panel is deferred (see below).

## Impact

- New table `session_player_configs` (migration `0008`), new router
  `/sessions/{id}/players`, new repository mixin, new runtime module
  `runtime/player_agents.py`.
- `builtin_tools.py` gains a shared child-spawn helper; `spawn_subagent`
  behaviour is unchanged for sessions without a player roster, so existing
  session tool lists are untouched.
- History envelopes gain an optional payload field; the history-service stores
  payloads verbatim and needs no change.
- eval-service attribution becomes exact for orchestrated games and unchanged
  for every existing recorded game.

## Non-goals

- **Dashboard UI panel.** The per-player roster editor in the Play config panel
  is deferred; concurrent work is in flight on those Hero UI components. This
  change ships the types, draft assembly, and API client so the panel is a
  presentation-only follow-up.
- **Automatic head-to-head comparison reporting.** eval-service already scores
  per player; a "config A vs config B" report view is a separate change.
- **Deeper nesting.** A player agent is a subagent and cannot spawn further
  subagents; that existing one-level limit is retained deliberately.
- **Rewriting the villain as an agent.** The villain is run by the game rules
  via game-service tools, as the real game does. It is not an LLM seat.
- **Per-player MCP server sets.** Player agents inherit the orchestrator's
  enabled MCP servers; there is no game-play reason for seats to differ here.

## Assumptions

- "Two LLMs playing with each other" means two *cooperating* player agents, one
  hero each, versus the game — not an adversarial matchup. The schema supports
  one to four seats; two is the documented default.
- Seat ids are `player1`..`playerN`, matching DragnCards' own seat naming and
  eval-service's `^player\d+$` seat regex, so attribution lines up end to end.
- Reasoning effort continues to travel inside `gateway_options.reasoning`, the
  shape the runtime, the dashboard, and eval-service's judge config already use.
  The player-config API accepts a typed `reasoning` object and folds it into
  `gateway_options` so callers do not hand-assemble it.
- Orchestrator "meta" moves (villain phase automation, phase advances) are
  emitted without a `player`, so eval-service falls back to its existing
  heuristic for them. Tagging those with a non-seat actor is deferred; every
  move that a *seat* makes is explicitly attributed, which is what the
  comparison needs.

## Capabilities

### New Capabilities

- `game-orchestration`: an orchestrator agent session SHALL run a full
  cooperative Marvel Champions game by coordinating one player agent per seat,
  driving the real round structure, and handling all meta responsibilities.

### Modified Capabilities

- `agent-orchestrator`: per-session player-agent configuration (provider, model,
  reasoning, skills) with inheritance, and spawning a child session from a named
  seat's configuration rather than the parent's.
- `llm-capabilities`: the `list_player_agents` and `prompt_player_agent`
  built-in tools available to master jobs on sessions with a player roster.
- `agent-move-evaluation`: explicitly recorded acting-player identity takes
  precedence over heuristic attribution.
