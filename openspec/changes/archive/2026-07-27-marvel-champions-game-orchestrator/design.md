# Design — Marvel Champions game orchestrator

## Shape of the thing

```
                        user (dashboard / API)
                                 |
                      PUT /sessions/{id}/players/player1  { model, reasoning, skills }
                      PUT /sessions/{id}/players/player2  { model, reasoning, skills }
                                 |
                                 v
                     +-----------------------------+
                     |  orchestrator agent session |  skill: marvel-champions-orchestrator
                     |  (master prompt job)        |  MCP: game-service
                     +-----------------------------+
                        |            |            \
        list_player_agents      prompt_player_agent("player1", ...)
                                     |                        \
                                     v                         v
                    +--------------------------+   +--------------------------+
                    | child session player1    |   | child session player2    |
                    | provider/model/reasoning |   | provider/model/reasoning |
                    | skills from its own row  |   | skills from its own row  |
                    | metadata.player_id=p1    |   | metadata.player_id=p2    |
                    +--------------------------+   +--------------------------+
                                     |                        |
                        game-service MCP tool calls (its own hero only)
                                     |                        |
                                     v                        v
                     history:ingest  ->  history-service  ->  eval-service
                     payload.player = "player1" / "player2"
```

The orchestrator itself also calls game-service directly for the villain phase
and phase transitions — the parts of the round that belong to the game, not to a
seat.

## Why child *sessions*, not a new primitive

The service already models delegation at the job level: `Job.parent_job_id`,
`spawn_subagent` creating a throwaway child `AgentSession`, `wait_for_subagent`
blocking on the live bus, cancellation cascading parent → children, child
sessions hidden from the session list, and child sessions terminated when their
job ends. All of that is exactly the lifecycle a player agent needs.

The only thing missing is that `spawn_subagent` copies the *parent's* model
config and skills onto the child. So the change is not a new execution model; it
is one extra input to child creation: "configure the child from this stored seat
config instead of from the parent". `prompt_player_agent` is therefore a thin
sibling of `spawn_subagent` over a shared `_spawn_child_agent` helper.

Consequence: a player agent is a subagent, so it has no `spawn_subagent` of its
own. That is correct — a player at a table does not delegate their turn.

## Where per-player config lives

A dedicated table, not session metadata:

```
session_player_configs
  session_id       FK agent_sessions ON DELETE CASCADE  ┐ composite PK
  player_id        'player1'..'player4'                 ┘
  display_name     nullable
  provider_id      nullable  -- NULL inherits the orchestrator session
  model_name       nullable  -- NULL inherits
  gateway_options  JSON      -- overlaid on the inherited gateway options
  provider_options JSON      -- overlaid on the inherited provider options
  skills_json      JSON      -- NULL inherits the orchestrator's enabled skills
  created_at, updated_at
```

Metadata JSON was rejected: the roster needs per-row upsert/delete, referential
integrity with the session, and validation at the API boundary. It also has to
survive process restarts and be readable by a different worker replica than the
one that wrote it — services hold no state in memory, so this is Postgres.

`NULL` means inherit, and that is load-bearing: a user comparing two
configurations usually changes *one* axis (model, or reasoning, or one skill)
and wants everything else identical. Inheritance makes "same except X" the
default rather than something the user has to keep in sync by hand.

## Resolution rules

`resolve_player_agent_config(parent_session, player_config)` is a pure function
so it is directly testable:

| Field | Rule |
| --- | --- |
| `provider_id` | seat value, else parent's |
| `model_name` | seat value, else parent's |
| `gateway_options` | parent's, overlaid with the seat's |
| `provider_options` | parent's, overlaid with the seat's |
| `reasoning` | folded into the resolved `gateway_options["reasoning"]`; `enabled: false` removes the key |
| `skills` | seat's list if set (even if empty), else the parent's enabled skills |
| MCP servers | always the parent's enabled servers |

Reasoning is stored *already folded* into `gateway_options` at write time, so
the runtime path stays identical to every other session: `payload.update
(gateway_options)` in `BifrostClient.chat_completion`, and
`PromptRunService.reasoning_enabled()` detecting the `reasoning` dict. The typed
`reasoning` request field exists purely so callers do not hand-assemble it, and
it is echoed back on read by unfolding the stored key.

## Player identity on the timeline

`prompt_player_agent` seeds the child session's metadata with `player_id`, and
also copies the orchestrator's `game_id` so the child's very first move already
knows which game it belongs to (otherwise the child would emit nothing until it
happened to call a game-id-source tool).

`PromptRunService._emit_agent_move_event` reads `metadata.player_id` and passes
it to the emitter, which puts it on `payload.player`. The envelope's
`idempotency_key` is unchanged (`game_id | actor | producer_offset`) — the
offset is already globally unique per game, and two seats never share one.

On the consuming side eval-service's `attribute_move` gains one new, highest
priority signal: an explicit `payload.player`. It is checked *before* the
"single player → player1" short-circuit, because an orchestrated game may not
have enough recorded `game-service` state for the seat count to be derivable,
and an explicitly recorded seat should never be overridden by a failure to infer
one. Games recorded before this change have no `payload.player` and keep their
existing heuristic attribution exactly.

## Tool registration

`list_player_agents` and `prompt_player_agent` are registered only when the
session actually has player configs. Two reasons: sessions that are not running
an orchestrated game should not see tools they cannot use, and every existing
test that asserts a session's tool list stays green.

`build_builtin_registry` therefore takes an optional pre-loaded
`player_configs` list. It is loaded once per job by the caller rather than
queried inside the registry builder, so the synchronous registry construction
stays synchronous and the preview path (`api/tool_catalog.py`) can reuse it.

## The skill

`skills/marvel-champions-orchestrator/SKILL.md` is the behavioural contract. It
is deliberately a *procedure*, not rules knowledge — the rules already live in
`marvel-champions-learn-to-play` and `marvel-champions-rules-reference`, which
the orchestrator loads on demand and which each player agent is normally
configured with too.

Two references keep `SKILL.md` scannable:

- `references/round-loop.md` — the exact tool sequence for each of the ten steps
  of a round, mapped onto game-service MCP tools.
- `references/player-turn-prompt.md` — the prompt contract for a seat's turn:
  what the orchestrator must include, what the player agent must return, and the
  boundaries a player agent must not cross.

The single most important instruction in the skill is the separation of
authority: the orchestrator never decides a hero's play, and a player agent
never touches another seat's cards or advances a phase. That separation is what
makes a per-player verdict mean something.
