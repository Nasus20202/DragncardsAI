# Eval Service (the judge)

On-demand LLM move-evaluation service for DragnCards agent play. A user selects
which moves/rounds of a recorded game to grade; the eval-service reads exactly
those events from the history-service, runs a fresh, stateless judge LLM through
the Bifrost gateway under a **dedicated `eval-judge` identity**, and writes each
structured verdict back onto the same per-game timeline as an `evaluator` event.

Evaluation is user-directed and idempotent: a target is graded at most once
(dedupe on `(game_id, target_seq, scope)`) unless `force` is set. A slow or
failing judge never blocks history ingestion or game play — eval only reads
committed events and writes advisory verdicts.

## Quick start

```bash
cd services/eval-service
uv sync
uv run eval-service        # serves on :4005 by default
```

## Configuration

All settings have secret-free defaults; the judge's provider credentials live in
Bifrost, not here (see [Judge identity](#judge-identity)), so the only secret in
this service's own configuration is `EVAL_DATABASE_URL`.
`EVAL_JUDGE_MODEL` is **required with no default** — the service refuses to
evaluate (and reports readiness `degraded`) until it is set. See `.env.example`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `EVAL_DATABASE_URL` | `postgresql+asyncpg://...:5443/eval_service` | Dedicated eval DB (its own) |
| `HISTORY_SERVICE_BASE_URL` | `http://localhost:4004` | History read + write-back |
| `BIFROST_URL` | `http://localhost:4003` | LLM gateway |
| `BIFROST_API_KEY` | `dummy` | Gateway auth token — does **not** select a provider key |
| `EVAL_JUDGE_MODEL` | _(required, unset)_ | `provider/model` judge id; the prefix picks the provider |
| `EVAL_JUDGE_PROVIDER` | _(optional)_ | Provider hint for verdict metadata |
| `EVAL_JUDGE_BIFROST_KEY_NAME` | `eval-judge` | Bifrost key entry judge traffic is pinned to (`x-bf-api-key`); `""` opts out |
| `EVALUATOR_VERSION` | `eval-2` | Recorded on every verdict; bump when what the judge is shown or asked changes, since scores are comparable only within one version. `eval-2` corrected round boundaries (see [Round boundaries](#round-boundaries)) *and* made a move judged in the context of its round |
| `EVAL_MAX_ATTEMPTS` | `3` | Retry attempts before skip |
| `EVAL_PER_GAME_CONCURRENCY` | `4` | Per-game in-flight judge cap, enforced by the durable claim |
| `EVAL_GLOBAL_CONCURRENCY` | `8` | Global in-flight judge cap (the provider-stampede guard), enforced by the durable claim |
| `EVAL_JUDGE_MAX_TOKENS` | `1024` | Per-evaluation token budget |
| `EVAL_JUDGE_MAX_STATE_CHARS` | `20000` | Backstop cap on each rendered state in the judge prompt (truncated + logged) |
| `EVAL_JUDGE_MAX_ROUND_MOVES` | `100` | Cap on per-move blocks listed in a round prompt |
| `EVAL_JUDGE_MOVE_CONTEXT_BEFORE` | `100` | Backstop on the earlier-in-round moves attached to a move prompt (the window is the round, not this number) |
| `EVAL_JUDGE_MOVE_CONTEXT_AFTER` | `100` | Backstop on the later-in-round moves attached (`0` removes hindsight) |
| `EVAL_JUDGE_MOVE_CONTEXT_REASONING_CHARS` | `400` | Per-move reasoning cap, in a move prompt's neighbour block and a round roll-up's move list alike |
| `EVAL_JUDGE_MAX_CHILD_RATIONALE_CHARS` | `600` | Per-child rationale cap in a roll-up prompt; their count is capped at `EVAL_JUDGE_MAX_ROUND_MOVES` |
| `SKILL_ROOTS` | repo `skills/` (`/app/skills` in the image) | `;`/`,`-separated roots searched for selected skills, by name — the same directory the agent-orchestrator discovers from |
| `EVAL_JUDGE_CONTEXT_WINDOW_TOKENS` | `128000` | The judge model's context window. This is what **bounds** a skill-reference selection, and the only setting that **raises** that bound. See [Rules skills and their references](#rules-skills-and-their-references) |
| `EVAL_JUDGE_MAX_SKILL_REFERENCE_CHARS` | `0` | Optional **extra** cap across a request's selected skill **reference files**. `0` = no cap beyond the context window; a positive value only ever *lowers* the derived budget, never raises it. Unlike the caps above this one **refuses** (400) rather than truncating |
| `EVAL_SKIP_NON_STRATEGIC_MOVES` | `true` | Skip actions that carry no strategic decision |
| `EVAL_NON_STRATEGIC_ACTIONS` | _(built-in taxonomy)_ | Replaces the skip list; anything unlisted is evaluated |
| `EVAL_CORS_ALLOW_ORIGINS` | `http://localhost:3001,http://127.0.0.1:3001` | Comma-separated CORS allowlist (dashboard reaches the service via a server-side proxy, so a strict list is safe) |

Standard OpenTelemetry variables (`OTEL_SERVICE_NAME`,
`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_RESOURCE_ATTRIBUTES`, `OTEL_SDK_DISABLED`)
are read too; see Observability below.

## Observability

Traces, metrics and logs are exported over OTLP/HTTP to `otel-lgtm` (Grafana on
http://localhost:3004). The bootstrap is `dragncards_common.telemetry`, bound to
this service's name in `eval_service/telemetry.py`; the instrumented edges are the
HTTP server, outbound HTTP (so judge calls through Bifrost are traced), and
PostgreSQL via SQLAlchemy. The worker opens one `eval.evaluate_target` span per
graded target, carrying the target/request identifiers, the scope and the outcome.

Set `OTEL_SDK_DISABLED=true` to run with telemetry off; the service is otherwise
unaffected. The judge prompt, the recorded state it is assembled from, the judge's
response, and gateway error text are never attached as span attributes — error
detail goes to the target row through `sanitize_error_detail` instead.

## What the judge is sent

A judge prompt is deliberately small, and small in the right places.

**State is projected, not clipped.** `game-service` records the *raw* DragnCards
room state on every `game_state` event — measured on real recorded games, ~450-470
KB per event, of which ~225 KB is `deltas` (DragnCards' internal undo/replay log)
and most of the rest is plugin configuration: layouts, automation action lists,
rule definitions, image URLs, and both faces of every card definition. Because
`deltas` sorts before `game` under canonical JSON, clipping that state to a
20,000-character budget produced a prompt made *entirely* of delta log: ~13,700
prompt tokens per move showing the judge no board at all.

`judge/state_view.py` instead projects the recorded state down to the same
`SimplifiedGameState` shape the game-service serves the playing agent — round,
phase, per-seat hit points and hand size, and per-zone card lists with instance
ids, types, traits and live tokens. Face-down cards and deck contents collapse to
a `HIDDEN` count, so hidden information stays hidden (and 60+ deck cards stop
being serialised). `EVAL_JUDGE_MAX_STATE_CHARS` remains as a backstop for a state
shape the projection does not recognise, which is sent as recorded.

**A move is judged in the context of its round.** A move prompt carries the agent
moves of the graded move's OWN ROUND, on both sides of it — the moves recorded
earlier in the round and the moves recorded later. The round is the window: the
context never reaches into an adjacent round (a different turn on a different
board) and never stops inside the round (which would hide the rest of the play).

This is what stops a good play being scored as several bad moves. A Marvel
Champions play is normally 2-4 tool calls — move the ally into play, exhaust a
character to pay the cost, assign the damage — and each call is its own recorded
`agent` event, so each becomes its own verdict. Asked "was this a strong strategic
choice toward winning?" about `exhaust_card` alone, a judge correctly answers
"no", and the play is marked down once per call. The round supplies the play; the
rubric's multi-call-play instruction (see `judge/prompt.py`) tells the judge to
grade the action as the step it is within that play, not to score down a necessary
step for achieving nothing alone, and not to charge one play against every action
that makes it up. The later-in-round half is labelled completion context, not an
outcome to grade on hindsight.

Actions the non-strategic taxonomy skips as *targets* still appear as *context*:
"searched for Med Team, then played Med Team" is more legible than "played Med
Team", and a one-line context entry is cheap.

`EVAL_JUDGE_MOVE_CONTEXT_BEFORE`/`_AFTER` remain only as backstops against a
pathological round, defaulting to the same ceiling `EVAL_JUDGE_MAX_ROUND_MOVES`
uses. They are not the mechanism. When no recorded state yet carries a round
number — during setup — no round contains the move, and the context falls back to
that many nearest moves across the timeline rather than none at all.

This supersedes the narrow fixed-count window (8 before / 3 after) that trimmed
the prompt to a measured 3,067 mean tokens per move: accuracy takes priority over
payload size, so the prompt is now bounded by the round instead. The projection
above is what did the heavy lifting on size (13,750 → ~3,000 tokens) and it
remains in place, so a round-scoped prompt still costs a fraction of the
pre-projection one.

## Rules skills and their references

A judge configuration can select **rules skills** by name (`judge.skills`) and
**individual reference files** of those skills (`judge.skill_references`). Both
resolve under `SKILL_ROOTS`, the same directory the agent-orchestrator discovers
skills from, so a name chosen in the dashboard means the same file in both
services.

```jsonc
"judge": {
  "skills": ["marvel-champions-rules-reference"],
  "skill_references": [
    "marvel-champions-rules-reference/resources/errata.md",
    "marvel-champions-rules-reference/resources/timing.md"
  ]
}
```

A selection is `"<skill-name>/<path-relative-to-the-skill>.md"` — the two
arguments the orchestrator's `load_skill_reference` tool takes, joined. The
agent-orchestrator's `GET /skills` reports each skill's `references`, which are
exactly the names accepted here.

**A reference may be selected without its skill.** "Give the judge only the
errata" is a legitimate configuration, and it would be an arbitrary tax to charge
it the whole `SKILL.md` to reach one file. References that arrive without their
skill are grouped under a `## Skill: <name> (references only)` heading, so the
judge is never told it holds the whole skill when it holds two files from it.

**Why the skill is inlined rather than fetched with a tool.** Agents call
`load_skill` because what an agent needs varies turn by turn. A judge runs the
same rubric against the same rules for every target, so a tool round trip would
return identical bytes on every call — and a judge that *declined* to call it
would still emit a well-formed verdict graded on no rules at all, with nothing in
the output to show it. Inlining also keeps a verdict's identity honest: the
write-back idempotency key hashes the resolved judge config, which only
identifies what the judge saw while the config fully determines the prompt.

**Why references are selected rather than inlined wholesale.** `SKILL.md` is
affordable — `marvel-champions-rules-reference` is 21,654 characters against a
move prompt's ~41,500 of rubric and projected state. Its 21 reference files are
256,568 characters, **nearly 12x its own `SKILL.md`**. The judge is single-shot
with no tool loop, so every selected byte is in the prompt on every graded
target; the selection is explicit so the operator, not the model, decides what
that costs.

### The reference budget is what the context window leaves

There is **no bound on how many references may be selected.** A count measures
nothing here — the rules skill's files span a 20x size range — so the only bound
is the total SIZE, and it is derived rather than fixed:

```
budget = EVAL_JUDGE_CONTEXT_WINDOW_TOKENS x 4 chars/token   # ~512,000 at the default
       - EVAL_JUDGE_MAX_TOKENS x 4                          # the completion has to fit
       - the WORST of the three scope reserves               # see below
       - 12,000                                             # rubric, labels, the graded move
       - len(prompt override)
       - the SKILL.md files this request selects
```

The scope reserve is a **max, not a sum** — one judge config serves all three
prompt shapes, and they hold different things, so adding them would reserve for a
prompt that cannot exist:

| scope | state | move context | roll-up context |
| --- | --- | --- | --- |
| move | 2 x `MAX_STATE_CHARS` | (`BEFORE` + `AFTER`) x (`REASONING_CHARS` + 400) | — |
| round | 1 x `MAX_STATE_CHARS` | `MAX_ROUND_MOVES` x (`REASONING_CHARS` + 400) | `MAX_ROUND_MOVES` x (`MAX_CHILD_RATIONALE_CHARS` + 200) |
| game | 1 x `MAX_STATE_CHARS` | — | `MAX_ROUND_MOVES` x (`MAX_CHILD_RATIONALE_CHARS` + 200) |

At the defaults the move prompt binds, and the budget is **295,904 characters** —
4.9x the 60,000 it replaced, and enough for all 21
`marvel-champions-rules-reference` files (256,568) alongside their `SKILL.md`
(21,654), with roughly 17,700 characters to spare. Selecting *every* reference of
*every* skill (338,790 across 35 files, plus 78,619 of `SKILL.md`) does **not**
fit a 128k window and is refused; raise `EVAL_JUDGE_CONTEXT_WINDOW_TOKENS` if
your judge model has the room.

Character counts are measured from `skills/`; **token figures are projections at
~4 chars/token, never measured** — no judge call is possible without
`EVAL_JUDGE_OPENROUTER_API_KEY`.

For the reserve to be a real ceiling the prompt has to honour it, so a round
roll-up now clips each move's `reasoning` at
`EVAL_JUDGE_MOVE_CONTEXT_REASONING_CHARS` (as a move prompt's neighbour block
already did) and bounds its child verdicts by both count
(`EVAL_JUDGE_MAX_ROUND_MOVES`) and rationale length
(`EVAL_JUDGE_MAX_CHILD_RATIONALE_CHARS`). A move's `arguments` stay unclipped —
legality is judged on them — and are covered by the per-line projection instead.

To fit more: raise `EVAL_JUDGE_CONTEXT_WINDOW_TOKENS` to your judge model's real
window, or lower `EVAL_JUDGE_MOVE_CONTEXT_BEFORE`/`_AFTER` (the largest reserve
term by far, and a *backstop* on a pathological round rather than the mechanism —
a real round is 6-10 moves, not 200). `EVAL_JUDGE_MAX_SKILL_REFERENCE_CHARS` only
ever *lowers* the budget; it cannot raise it above what the window admits,
because doing so never worked — it bought a provider error later instead of a 400
now. `MAX_SKILL_REFERENCES` (1,000) remains on the schema purely to reject an
absurd request body before anything is read from disk.

**References are never truncated.** State is clipped to fit a prompt because a
clipped board is still a board; a clipped rules reference reads to the judge
exactly like a complete one. Over budget is a 400, raised in
`resolve_judge_config` before any target is enqueued, and it states the measured
total, the budget, the overage, every reserve term, and the settings that would
change them — the skills catalogue reports reference *names* only, so the
dashboard cannot warn before the request is made and the refusal is where the
user learns why.

**Reference paths are confined to their own skill.** A selection is
caller-supplied, so `judge/skill_resources.py` refuses an absolute path, any `..`
component, a non-canonical form, a symlink anywhere along the path, a non-`.md`
file, a directory, and the skill's own `SKILL.md`. Every refusal carries the same
message, so it cannot be used to probe for files outside the skill.

Selecting references changes the judge config digest, so a re-evaluation with
references is recorded as a distinct verdict rather than deduplicated against one
graded without them. A config that selects **no** references hashes exactly as it
did before references existed, so nothing already recorded stops deduplicating —
which is why `EVALUATOR_VERSION` is not bumped for this: the digest already
distinguishes the two regimes precisely, and bumping would invalidate every
`eval-2` verdict whose prompt is provably unchanged.

## Orchestrated play is projected as orchestrated

The projection states the session mode the play was recorded in. When it is
`orchestrated` it also states that each player seat was a **separate agent holding
its own context and its own persona**, so the judge does not mark a seat down for
failing to account for information it could not have seen. When it is `chat` the
projection reads exactly as it did before orchestrated mode existed — byte for byte —
so verdicts recorded either side of the change stay comparable.

A round additionally carries the **illegal-action findings** the orchestrator recorded
inside it, naming the seat, the violation, and whether it was resolved or is still
open. The judge no longer has to infer a rules violation from the move list when
legality was already decided from game state, and a finding is presented as evidence
to weigh alongside everything else rather than as a verdict that settles the score by
itself. A finding naming a seat other than the one being scored is shown as
explaining the position the round produced, not as that seat's play to answer for.

An `illegal_action` finding is an `agent` event but **not a move**: history-service
pins `actor` to a fixed set, so a new orchestrator concern arrives as a new event type
under the existing actor. `judge/events.py::is_agent_move` is the single predicate
that tells the two apart, and it is what keeps a finding from being graded as a play,
attributed to a seat as an action, or counted into a round's move total.

## Non-strategic actions are skipped, visibly

Not every recorded `agent_move` is a play a judge can grade. The dividing line is
**not** whether a tool reads or writes, but whether the action commits game state
in a way a player could get wrong: *searching* for a card cannot be a wrong
decision, *taking* one into hand can be. So `search_cards_marvel_champions` is
non-strategic while `draw_card` and `move_card` are strategic.

Three non-strategic categories (see `judge/actions.py`):

| Category | Actions | Why |
| --- | --- | --- |
| Read-only | `get_game_state`, `get_session_actions`, `list_actions`, `list_card_providers`, `list_games`, `lookup_session_by_slug`, `search_cards_marvel_champions`, `search_prebuilt_sets_marvel_champions` | Return information, change nothing on the table |
| Session plumbing | `attach_game`, `create_game`, `delete_game` | Room lifecycle, outside the game |
| Pre-game setup | `load_cards`, `load_prebuilt_deck`, `multiple_double_sided_villains`, `set_player_count_action`, `unload_cards` | Establish the starting position rather than play from it; none of the rubric's criteria apply |

Everything else is **evaluated**, including the borderline mechanical ones —
`ready_card`, `zero_tokens`, `next_step`/`prev_step` and the phase tools — because
each commits state a player can get wrong (readying the wrong card, ending the
player phase with actions unspent). Any action the taxonomy does not recognise is
evaluated too: wrongly skipping a strategic action degrades evaluation quality
where nobody will notice, while wrongly evaluating a trivial one only costs one
judge call.

A skipped target is recorded as `skipped` with the reason on the target row, so it
can never be mistaken for a passing verdict. `skipped` means "there was no
decision to grade here" and nothing else — a judge or assembly *failure* is
recorded as `failed` (see [Errors are reported live](#errors-are-reported-live)),
so a deliberate skip and an error are never conflated. Round roll-ups leave
non-strategic moves out of their move list and state how many were omitted. On the
recorded games in this stack this skips **32.0% of agent moves**.

## Errors are reported live

An evaluation that hits an error says so **while it is running**, with the reason,
not only as a terminal status:

- **`failed` is for errors, `skipped` is for "nothing to grade".** A judge call
  that exhausts its retries, an assembly error, an undetected round boundary, an
  unreadable timeline, a failed write-back and a missing `EVAL_JUDGE_MODEL` all
  record the target as `failed` with the reason on `error`. Only a non-strategic
  action is `skipped`.
- **Every failed attempt is recorded as it happens.** A retried judge attempt
  writes its reason to the target row *while the row is still `running`*, so
  `GET /games/{id}/evaluations/{request_id}`, the cross-game `GET /evaluations`
  listing and the SSE stream all report it immediately. Nothing is held in the
  worker — the detail lives in Postgres, so any replica or poller reads the same
  thing. The dashboard's evaluations queue lists these per-target failures on the
  request row on its normal refresh, so a problem is visible mid-run.
- **The live channel is woken on every recorded failure**, so a connected SSE
  client re-reads the snapshot at once rather than waiting for the next transition.
- **Detail is redacted and truncated.** `error_detail.sanitize_error_detail` runs
  at the repository boundary on every recorded error: `Authorization`/`Bearer`
  values, `x-bf-api-key`, `api_key`/`access_token`/`client_secret`/`password`
  fields and bare provider key literals (`sk-…`, `sk-or-v1-…`, `xai-…`, `gsk_…`,
  `AIza…`) become `[REDACTED]`, and the text is capped at 1,000 characters so a
  provider echoing the full request body (prompt and recorded game state) cannot
  be persisted or pushed to a client.

## Judge identity

The judge runs on its own provider credential, for **any** provider — not just
Anthropic. The mechanism is Bifrost's named-key selection:

1. Each provider in `services/bifrost/config.json` carries a second key entry
   named `eval-judge` at `"weight": 0.0`, sourced from its own
   `env.EVAL_JUDGE_<PROVIDER>_API_KEY`. Weight `0.0` keeps it out of normal
   gameplay key selection, which is weighted-random over the provider's keys.
2. Every judge call sends `x-bf-api-key: eval-judge` (from
   `EVAL_JUDGE_BIFROST_KEY_NAME`). Bifrost resolves that header to the
   same-named key of whichever provider the model id routes to, and explicit
   selection overrides the `0.0` weight.

`Authorization: Bearer` is gateway auth only — with `enforce_auth_on_inference:
false` and `allow_direct_keys: false` it selects nothing, so the
`x-bf-api-key` header is what makes the dedicated identity real.

**Adding a judge key for another provider** — e.g. to judge with
`EVAL_JUDGE_MODEL=openrouter/anthropic/claude-sonnet-4`:

1. Ensure that provider has an `eval-judge` key entry in
   `services/bifrost/config.json` (all shipped providers already do).
2. Set `EVAL_JUDGE_OPENROUTER_API_KEY` in `services/bifrost/.env` (never
   committed).
3. Restart Bifrost so it re-reads `config.json` and the environment.

**Misconfiguration is loud, never silent.** Judge traffic can never quietly fall
back to a game-playing key:

- `GET /ready` reports `judge_key: {name, provider, status, providers}` and
  returns `degraded` when `status` is `missing` — the configured provider has no
  `eval-judge` entry. `providers` lists the providers that do, so switching is an
  informed choice. `status: unknown` means Bifrost's key listing was unreadable;
  `disabled` means `EVAL_JUDGE_BIFROST_KEY_NAME` was deliberately emptied (also
  warned at startup).
- If the key is missing or its `env.` reference is unset, Bifrost rejects the
  call with `no supported key found with name "eval-judge" for provider: <p>`.
  That is a definitive 4xx, so it is not retried, and the message is recorded as
  the target's `failed` reason and shown in the UI.

## HTTP API

- `POST /games/{game_id}/evaluations` — request evaluation of selected targets.
  Body: `{ "scope": "move"|"round", "selection": { ... }, "force": bool,
  "judge": { ... } }`. The optional `judge` object overrides the server defaults
  for this evaluation only — provider, model, reasoning, `prompt_override`,
  `skills` and `skill_references` (see
  [Rules skills and their references](#rules-skills-and-their-references)). It is
  resolved and validated first, so an unknown skill or an unresolvable /
  over-budget reference is a `400` before any target is enqueued.
  Returns `201` with created/skipped counts and the target list.
- `GET  /games/{game_id}/evaluations/{request_id}` — per-target status + verdicts.
- `GET  /games/{game_id}/evaluations` — list a game's requests (UI polling).
- `GET  /games/{game_id}/rounds` — the rounds this service detects for a game, so
  a client can select a ROUND without naming a sequence inside it. Each entry
  carries the raw `round_number` that `selection.rounds` accepts, its display
  `label` (the round *of play*, `round_number + 1`, because DragnCards counts
  COMPLETED rounds and so reports 0 throughout the first round), the `from_seq`/
  `to_seq` span, the `move_count`, and the acting `players`. `404` when the game
  has no recorded events.
- `GET  /health`, `GET /ready` — liveness/readiness (db + history + bifrost +
  judge model/key; names only, no secrets).

### Selection shape

```json
{
  "scope": "move",
  "selection": {
    "seqs": [12, 18],
    "rounds": [1, 2],
    "seq_range": { "from_seq": 1, "to_seq": 50 },
    "whole_game": false
  },
  "force": false
}
```

For `scope=move`, `seqs`/`seq_range`/`whole_game` select agent move seqs. For
`scope=round`, `rounds` is the direct way in — the raw round numbers from
`GET /games/{game_id}/rounds` — and `seqs`/`seq_range`/`whole_game` also resolve
to the rounds they fall inside. Rounds are detected from the round number on
`game-service` state events with a terminal-status fallback for the final round.

Selecting a round needs only its number. Resolving a mid-round `seq` to its
containing round is kept for clients that have a sequence and not a round number,
but it is no longer how the dashboard picks a round.

`rounds` names rounds of **play**, 1-based — the same numbers the History tab
shows. See [Round boundaries](#round-boundaries).

### Round boundaries

A round span comes from the raw `roundNumber` on `game-service` state events, and
two DragnCards facts decide where it starts and ends:

- A `game-service` event embeds the state **after** its action was applied, so the
  event whose state first reports a new `roundNumber` is the event that **closed**
  the previous round. That event is the round's last seq (`to_seq`), and the next
  round starts at the seq after it. A round roll-up therefore sees the board as
  its own round ended, and the closing move is graded inside the round it closed.
- `roundNumber` counts **completed** rounds — it reads 0 for the whole first round
  of play — so every round number the service reports or accepts (`selection.rounds`,
  the round named in the judge prompt) is `roundNumber + 1`. This matches the
  History tab, so a verdict and the transcript name the same round.

Both were wrong before `EVALUATOR_VERSION=eval-2`: spans were shifted by one event
at each boundary and rounds were named by the raw counter. Round and game verdicts
recorded under `eval-1` graded a different span from the one their round span now
denotes and are **not** comparable to `eval-2` verdicts; `evaluator_version` on
each verdict is what tells them apart. Move verdicts are unaffected by boundaries
(only their `evaluator_version` tag changes).

## MCP surface

The same HTTP API is exposed as MCP tools over streamable-HTTP at
http://localhost:4005/mcp/ (clients address it with the trailing slash). It exists
so an assistant working in this repository can grade a recorded game as tool calls —
list the rounds detected for a game, request an evaluation of a selection of them,
poll it until it finishes, read the verdicts, cancel a run — instead of
hand-written `curl` against endpoints whose shape it has to guess. The transport is
mounted in `main.py`, not in the app factory, so the test suites never start the MCP
session manager.

Tools are **generated from this service's OpenAPI schema** by
`dragncards_common.mcp`, so a tool is exactly the endpoint it came from and a
tool's name is that endpoint's `operation_id`: `list_game_rounds`,
`create_evaluation`, `get_evaluation`, `cancel_evaluation`, `list_evaluations`,
`delete_evaluation`.

`eval_service/mcp_server.py` lists what is kept out:

| Not a tool | Why |
| --- | --- |
| `stream_evaluation` | Server-sent events: a tool call reads its response to completion and this one only completes when the run does — poll `get_evaluation`, which also carries the live per-target error detail |
| `clear_evaluations` | Deployment-global bulk delete, including requests the caller never created; `delete_evaluation` for one request stays available so an agent can clean up after itself |
| `health`, `ready` | Probes are noise in an LLM's tool list |

Exclusion applies to MCP only; every one of those endpoints still works over HTTP.

**An evaluation over MCP still needs a configured judge.** `create_evaluation`
accepts the request either way, but with no `EVAL_JUDGE_MODEL` (and the routed
provider's `EVAL_JUDGE_<PROVIDER>_API_KEY`) set, `GET /ready` reports `degraded`
and every target is recorded as `failed` with the configuration error as its
reason. See [Judge identity](#judge-identity).

The end-to-end debugging loop these tools exist for is documented in
[`AGENTS.md`](../../AGENTS.md#driving-the-system-end-to-end).

## Verdict (evaluator event payload)

```json
{
  "scope": "round",
  "target_seq": 63,
  "round_span": [1, 63],
  "round_number": 1,
  "scores": { "rules_legality": 8, "strategic_quality": 6,
              "tempo_efficiency": 7, "threat_resource": 7 },
  "overall_score": 7,
  "rationale": "short paragraph",
  "flags": ["illegal_move"],
  "evaluator": { "model": "...", "provider": "...", "evaluator_version": "eval-2" }
}
```

`round_span` and `round_number` are **not** the same kind of number, and neither is
derived from the other:

- `round_span` is `[from_seq, to_seq]` — event sequence numbers on the game
  timeline. It is what seq-correlates a round or game verdict to the events it
  graded. A game verdict's span is the whole game; a move verdict has none.
- `round_number` is the 1-based round of **play** (`round_of_play()`, the raw
  `roundNumber` + 1) — the number the History transcript and
  `GET /games/{game_id}/rounds` name that round by. It is set for `scope=round`
  only: a move is named by its own seq, and a game verdict spans every round.

A consumer labels a round verdict from `round_number`, never from `round_span`:
reading the span's two elements as round numbers labels the first round of the game
above "Rounds 1–63" (DRA-25). Verdicts recorded before `round_number` existed — all
`eval-1` verdicts and the earliest `eval-2` ones — do not carry it and are labelled
without a round number rather than having one inferred from their span. Adding the
field changed neither the prompt, the graded span, nor the score scale, so it did
not move `EVALUATOR_VERSION`.

Written back via `POST {history}/games/{game_id}/events` as actor `evaluator`,
event_type `evaluation`, with
`idempotency_key = sha256(game_id|target_seq|scope|evaluator_version)`.

## Testing

```bash
uv run pytest tests/unit -q          # Unit tests (sqlite + stubs)
uv run pytest tests/integration -v   # Integration (needs Postgres)
```
