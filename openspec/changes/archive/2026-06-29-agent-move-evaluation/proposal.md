## Why

The history-event-store now captures, per game, every agent move/decision (intended action + reasoning + full conversation context) and every resulting game-state/status event, correlated under one `game_id` and ordered by a gap-free per-game `seq`. The data is deliberately "rating-ready," but the rating engine itself was explicitly deferred. Today nothing scores how well the game-playing LLM actually played: there is no automated, repeatable, per-move and per-round assessment of rules-legality and strategic quality. Without it we cannot compare models/prompts, catch regressions, or surface bad play for review.

We need a dedicated, cloud-native **evaluation service ("the judge")** that, on user request, evaluates **selected** moves/rounds of a recorded game **in isolation** with a separate judge LLM and writes the verdict back onto the same per-game timeline as a new `evaluator` event — so evaluations sit `seq`-correlated next to the moves they grade and surface on the existing history timeline. Evaluation is user-directed (the user chooses which game/turns/moves to analyze), not automatic.

## What Changes

- Add a new `eval-service` (Python/FastAPI, mirroring `agent-orchestrator` / `history-service`) with a dedicated PostgreSQL for evaluation requests, bookkeeping, and idempotency, exposing an **on-demand evaluation request API** (the user selects which moves/rounds/range/whole game to evaluate). No in-memory state. No automatic per-event evaluation.
- **history-service** SHALL accept `evaluator` as a third allowed envelope actor so verdicts can be ingested onto the same timeline, and SHALL exclude `evaluator` events from restore replay.
- On a user request, the eval-service SHALL evaluate only the selected targets (**per individual move** and/or **per round/turn**), reading the events it needs from the history-service, idempotently (dedupe on `game_id` + target `seq` + scope) unless the user forces re-evaluation.
- The judge LLM SHALL run **in isolation** — a fresh judge session per evaluation, not the game-playing agent's session — seeing the game state, the move taken, and the playing agent's reasoning/context for that move, and SHALL run under a **dedicated Bifrost virtual key/provider entry** with its own budget so judge traffic is recognizable and isolated from game traffic. Model/provider are configurable.
- The eval-service SHALL write each verdict back through the history-service HTTP ingest endpoint as an `evaluator` event whose payload carries per-criterion scores (e.g. rules-legality, strategic-quality), an overall score, a rationale, and the target move `seq` or round identifier.
- A failed/slow judge call SHALL retry then skip, and SHALL never block history ingestion or game play.
- **dashboard** SHALL provide a control to select which game/turns/moves to evaluate and trigger the request, and SHALL surface `evaluator` events and their scores on the existing game history timeline.
- **infrastructure** SHALL add the `eval-service` (and its dedicated PostgreSQL) to Docker Compose and a dedicated `eval-judge` Bifrost virtual key/provider entry with secret-free defaults.
- Add unit and integration tests alongside each feature: on-demand evaluation requests, per-move and per-round evaluation, evaluator-event write-back, idempotency + forced re-evaluation, dedicated-identity routing, and judge-failure isolation.

## Non-goals

- No change to how the game-playing agent decides moves, and no feedback loop where verdicts influence live play. Evaluation is read-only/after-the-fact.
- No human-in-the-loop review workflow, leaderboards, or cross-game aggregate analytics beyond surfacing per-game evaluator events on the existing timeline.
- No change to the upstream DragnCards Elixir backend or Marvel Champions plugin.
- No new restore/replay semantics; the eval-service consumes the existing timeline and does not mutate game state or run game-mutating actions.
- No retraining/fine-tuning of any model; the judge is prompt-driven and model-agnostic.

## Capabilities

### New Capabilities

- `agent-move-evaluation`: the eval-service — accept on-demand evaluation requests for user-selected targets, evaluate per-move and per-round with an isolated judge LLM under a dedicated Bifrost identity, write `evaluator` verdict events back to history idempotently (with forced re-evaluation), and isolate judge failures from play.

### Modified Capabilities

- `history-event-store`: SHALL accept the `evaluator` actor on the event envelope and SHALL exclude `evaluator` events from restore replay.
- `game-history-ui`: the dashboard SHALL let the user select targets and request evaluation, and the history timeline SHALL surface `evaluator` events and their scores against the move/round they grade.
- `infrastructure`: add the `eval-service` and its optional dedicated PostgreSQL to Docker Compose, and add a dedicated `eval-judge` Bifrost virtual key/provider entry with external secrets.

## Impact

- New service code under `services/eval-service/` with its own settings, on-demand evaluation request API + worker, judge integration, schema/migrations, and tests.
- One additive change to history-service: an extended allowed-actor set (`agent` | `game-service` | `evaluator`) and exclusion of `evaluator` events from restore replay. Existing ingestion contracts are otherwise unchanged.
- New dashboard rendering for evaluator events on the timeline.
- New Docker Compose entries and environment configuration for the eval-service, its database, and the dedicated Bifrost judge identity.
