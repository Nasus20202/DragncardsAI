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
| `EVALUATOR_VERSION` | `eval-1` | Recorded on every verdict |
| `EVAL_MAX_ATTEMPTS` | `3` | Retry attempts before skip |
| `EVAL_PER_GAME_CONCURRENCY` | `2` | Per-game in-flight judge cap |
| `EVAL_GLOBAL_CONCURRENCY` | `8` | Global in-flight judge cap |
| `EVAL_JUDGE_MAX_TOKENS` | `1024` | Per-evaluation token budget |
| `EVAL_JUDGE_MAX_STATE_CHARS` | `20000` | Backstop cap on each rendered state in the judge prompt (truncated + logged) |
| `EVAL_JUDGE_MAX_ROUND_MOVES` | `100` | Cap on per-move blocks listed in a round prompt |
| `EVAL_JUDGE_MOVE_CONTEXT_BEFORE` | `8` | Preceding agent moves included with a move prompt |
| `EVAL_JUDGE_MOVE_CONTEXT_AFTER` | `3` | Following agent moves included (`0` removes hindsight) |
| `EVAL_JUDGE_MOVE_CONTEXT_REASONING_CHARS` | `400` | Per-neighbour reasoning cap |
| `EVAL_SKIP_NON_STRATEGIC_MOVES` | `true` | Skip actions that carry no strategic decision |
| `EVAL_NON_STRATEGIC_ACTIONS` | _(built-in taxonomy)_ | Replaces the skip list; anything unlisted is evaluated |
| `EVAL_CORS_ALLOW_ORIGINS` | `http://localhost:3001,http://127.0.0.1:3001` | Comma-separated CORS allowlist (dashboard reaches the service via a server-side proxy, so a strict list is safe) |

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

**History is a window, not a replay.** A move prompt carries the agent's
`EVAL_JUDGE_MOVE_CONTEXT_BEFORE` preceding and `EVAL_JUDGE_MOVE_CONTEXT_AFTER`
following moves, not the whole timeline. The correlated prior/resulting board
already summarises everything that happened earlier, so replaying the full move
list adds cost without signal. What a board *cannot* show is that one tool call is
a fragment of a larger play — a Marvel Champions play is typically 2-4 calls (play
the card, assign damage, exhaust the character) and a player turn runs ~6-10 — and
judging a fragment alone invites a confidently wrong verdict, which is worse than
a slow one. The defaults cover a typical turn's worth of preceding calls plus
enough following calls to see whether a play completed; the following half is
labelled in the prompt as completion context, not an outcome to grade.

Measured on the recorded games in this stack: **13,750 → 3,067 mean prompt tokens
per move evaluation (−77.7%)**, while the judge gains a board it never had.

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

A skipped target is recorded as `skipped` with the reason on the target row — the
same channel a judge failure uses — so it can never be mistaken for a passing
verdict. Round roll-ups leave non-strategic moves out of their move list and state
how many were omitted. On the recorded games in this stack this skips **32.0% of
agent moves**.

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
  the target's skip reason and shown in the UI.

## HTTP API

- `POST /games/{game_id}/evaluations` — request evaluation of selected targets.
  Body: `{ "scope": "move"|"round", "selection": { ... }, "force": bool }`.
  Returns `201` with created/skipped counts and the target list.
- `GET  /games/{game_id}/evaluations/{request_id}` — per-target status + verdicts.
- `GET  /games/{game_id}/evaluations` — list a game's requests (UI polling).
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
`scope=round`, `rounds`/`seqs` (round-closing seqs)/`seq_range`/`whole_game`
select closed rounds, detected from the round number on `game-service` state
events with a terminal-status fallback for the final round.

## Verdict (evaluator event payload)

```json
{
  "scope": "move",
  "target_seq": 12,
  "round_span": [10, 18],
  "scores": { "rules_legality": 8, "strategic_quality": 6,
              "tempo_efficiency": 7, "threat_resource": 7 },
  "overall_score": 7,
  "rationale": "short paragraph",
  "flags": ["illegal_move"],
  "evaluator": { "model": "...", "provider": "...", "evaluator_version": "eval-1" }
}
```

Written back via `POST {history}/games/{game_id}/events` as actor `evaluator`,
event_type `evaluation`, with
`idempotency_key = sha256(game_id|target_seq|scope|evaluator_version)`.

## Testing

```bash
uv run pytest tests/unit -q          # Unit tests (sqlite + stubs)
uv run pytest tests/integration -v   # Integration (needs Postgres)
```
