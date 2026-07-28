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
| `EVAL_JUDGE_MAX_STATE_CHARS` | `20000` | Cap on each per-event state JSON in the judge prompt (truncated + logged) |
| `EVAL_JUDGE_MAX_ROUND_MOVES` | `100` | Cap on per-move blocks listed in a round prompt |
| `EVAL_CORS_ALLOW_ORIGINS` | `http://localhost:3001,http://127.0.0.1:3001` | Comma-separated CORS allowlist (dashboard reaches the service via a server-side proxy, so a strict list is safe) |

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
