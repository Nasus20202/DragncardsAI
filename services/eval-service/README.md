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

All settings have secret-free defaults; secrets live only in
`EVAL_DATABASE_URL` and `BIFROST_API_KEY` (the dedicated judge key).
`EVAL_JUDGE_MODEL` is **required with no default** — the service refuses to
evaluate (and reports readiness `degraded`) until it is set. See `.env.example`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `EVAL_DATABASE_URL` | `postgresql+asyncpg://...:5443/eval_service` | Dedicated eval DB (its own) |
| `HISTORY_SERVICE_BASE_URL` | `http://localhost:4004` | History read + write-back |
| `BIFROST_URL` | `http://localhost:4003` | LLM gateway |
| `BIFROST_API_KEY` | `dummy` | Dedicated `eval-judge` virtual key |
| `EVAL_JUDGE_MODEL` | _(required, unset)_ | `provider/model` judge id |
| `EVAL_JUDGE_PROVIDER` | _(optional)_ | Provider hint for verdict metadata |
| `EVALUATOR_VERSION` | `eval-1` | Recorded on every verdict |
| `EVAL_MAX_ATTEMPTS` | `3` | Retry attempts before skip |
| `EVAL_PER_GAME_CONCURRENCY` | `2` | Per-game in-flight judge cap |
| `EVAL_GLOBAL_CONCURRENCY` | `8` | Global in-flight judge cap |
| `EVAL_JUDGE_MAX_TOKENS` | `1024` | Per-evaluation token budget |
| `EVAL_JUDGE_MAX_STATE_CHARS` | `20000` | Cap on each per-event state JSON in the judge prompt (truncated + logged) |
| `EVAL_JUDGE_MAX_ROUND_MOVES` | `100` | Cap on per-move blocks listed in a round prompt |
| `EVAL_CORS_ALLOW_ORIGINS` | `http://localhost:3001,http://127.0.0.1:3001` | Comma-separated CORS allowlist (dashboard reaches the service via a server-side proxy, so a strict list is safe) |

## HTTP API

- `POST /games/{game_id}/evaluations` — request evaluation of selected targets.
  Body: `{ "scope": "move"|"round", "selection": { ... }, "force": bool }`.
  Returns `201` with created/skipped counts and the target list.
- `GET  /games/{game_id}/evaluations/{request_id}` — per-target status + verdicts.
- `GET  /games/{game_id}/evaluations` — list a game's requests (UI polling).
- `GET  /health`, `GET /ready` — liveness/readiness (db + history + bifrost; no secrets).

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
