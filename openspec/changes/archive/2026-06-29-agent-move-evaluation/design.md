## Context

The history-event-store (now archived) gives us the durable substrate this change builds on:

- A dedicated `history-service` (FastAPI + dedicated PostgreSQL) stores a per-game append-only event log. Every event is a versioned envelope `{ envelope_version, game_id, seq, event_type, actor, payload, occurred_at, recorded_at, idempotency_key, producer_offset }`. `seq` is a gap-free monotonic integer assigned by history at commit time under a per-game advisory lock. The allowed `actor` set is currently `agent | game-service` (the envelope explicitly rejects any other actor).
- **agent** events carry the intended action, the agent's reasoning/context, the action arguments, and the full conversation context the agent had at that decision.
- **game-service** events carry the resulting game-state representation and the game status (`in progress` / `win` / `loss`).
- Ingestion is dual-source: primary path is a shared Valkey stream `history:ingest` (consumer group `history-service`, at-least-once); a secondary authenticated HTTP endpoint `POST /games/{game_id}/events` accepts the same envelope. Idempotency is enforced by a unique `(game_id, idempotency_key)` constraint; duplicates are stored at most once and never consume a `seq`.
- The dashboard `game-history-ui` already renders a per-game timeline ordered by `seq`, distinguishing `agent` from `game-service` events.

The agent-orchestrator routes all LLM execution through the Bifrost gateway (`services/bifrost/config.json`), with provider entries (openai, anthropic, gemini, mistral, openrouter, nvidia, lmstudio) keyed by env-backed API keys. Sessions choose provider + model; history-service already knows the game-service base URL and orchestrator base URL.

This change adds the consumer of that "rating-ready" data: an evaluation service that grades play and writes verdicts back onto the same timeline.

## Goals / Non-Goals

**Goals:** an automated, repeatable judge that scores each agent move and each round in isolation; verdicts written back as a first-class `evaluator` event on the same per-game timeline (`seq`-correlated); a dedicated, budget-isolated Bifrost identity for judge traffic; at-least-once + idempotent evaluation (a target is judged at most once); strict failure isolation so the judge never blocks ingestion or play.

**Non-Goals:** the judge does not influence live play (no feedback loop); no human review workflow, leaderboards, or cross-game aggregates; no game-state mutation/replay; no upstream DragnCards changes; no model training.

## Decisions

### 1. A separate `services/eval-service/` FastAPI service, mirroring history-service

Rationale: Evaluation is a distinct failure domain and workload (bursty LLM calls, its own budget, its own ret/skip policy) that must be decoupled from both the durable record (history-service) and live play (orchestrator). A standalone stateless FastAPI service matches the repo precedent (orchestrator and history-service each own their service boundary and, where needed, their own PostgreSQL). It can scale horizontally and be deployed/operated independently. No in-memory state: queue offsets live in Valkey, idempotency/bookkeeping in PostgreSQL.

Alternatives considered: (a) Fold evaluation into history-service — rejected: couples LLM-call latency, budget, and failure modes to the durable write path; a slow/failing judge could threaten ingestion throughput, violating the "never block ingestion" goal. (b) Fold into agent-orchestrator — rejected: the orchestrator owns live play; mixing the judge in risks the judge sharing the game-playing identity/budget and re-using a game session, which contradicts "evaluate in isolation." (c) A serverless/cron batch job over PostgreSQL — rejected: loses the near-real-time, event-driven timeline correlation and reintroduces polling; revisit only if per-event evaluation proves too costly.

### 2. Trigger: an on-demand evaluation request API (user-selected targets), not an automatic queue

Evaluation is **user-directed**: the eval-service exposes a request API (e.g. `POST /games/{game_id}/evaluations`) where the user selects what to evaluate — specific move `seq`s, round(s), a `seq` range, scope `move`/`round`, or the whole game, with an optional `force` re-evaluate flag. The eval-service expands the selection into concrete targets, claims them idempotently, reads exactly the events it needs from the history read API (`GET /games/{game_id}/events`), runs the judge per target, and writes verdicts back. There is **no automatic per-event evaluation** and no history→eval publish hook; history is only read on demand. Requests may be processed synchronously or handed to an internal worker; a request-status endpoint reports per-target progress.

Rationale: The product decision is that the user chooses which game/turns/movements to analyze rather than spending a judge call on every move automatically — this controls cost and keeps evaluation deliberate. Reading the durable history read API on request (rather than consuming a push stream) is exactly right here: the targets and their `seq`s already exist in the committed log, so there is nothing to stream — the request names the targets directly.

Alternatives considered: (a) Automatic per-event queue (`eval:ingest` consumer group, history publishes each committed event) — this was the original design; rejected/deferred per the product decision to make evaluation user-selected and avoid an LLM call per move. It remains a possible *future* "auto mode," out of scope here. (b) eval polls history on a timer — rejected: no need; requests are explicit and name their targets.

### 3. Idempotency: dedupe on `(game_id, target_seq, scope)` so a target is evaluated at most once

`eval:ingest` is at-least-once, so duplicates are expected. The eval-service records each completed evaluation keyed by `(game_id, target_seq, scope)` where `scope` is `move` or `round`. Before evaluating it checks/claims the key (PostgreSQL unique constraint with `ON CONFLICT DO NOTHING`, or a Valkey `SET NX` claim that is finalized in PostgreSQL on success); a conflict means already-evaluated (or in-flight) and the stream entry is simply `XACK`ed without a second judge call. The verdict write-back to history also carries an `idempotency_key = hash(game_id, target_seq, scope, evaluator_version)` so even if the same verdict is written twice, history stores it once.

Rationale: `seq` is the natural, server-assigned, gap-free target identifier already present on every committed event, so it is the correct dedupe dimension — unlike the move's own contents which may not be unique. Including `scope` lets a single underlying `seq` carry both a move verdict and (when it closes a round) a round verdict without collision. Including `evaluator_version` lets a deliberate re-evaluation campaign (new judge prompt/model) produce a distinct verdict rather than being silently deduped.

Alternatives considered: (a) Dedupe on the history `idempotency_key` of the move event — rejected: that key dedupes *inbound producer* duplicates, not *evaluation* duplicates; two eval consumers processing the same `eval:ingest` entry need an eval-side key. (b) Best-effort in-memory dedupe — rejected: violates "no in-memory state" and is unreliable across replicas.

### 4. Judge input assembly: move event + correlated agent reasoning + game state, read from history

For a per-move evaluation of a target `seq`, the eval-service assembles the judge's input from the durable record (history read API), not from the live producers:

- The **move/action** and the **playing agent's reasoning/context** come from the `agent` move/decision event (it already carries intended action, reasoning, action arguments, and the full conversation context the agent had).
- The **game state** comes from the correlated `game-service` state event for that move (its payload carries the resulting game-state representation and status). When a move-then-state pair straddles two `seq` values, eval correlates the nearest `game-service` state event at or after the move's `seq` as the "resulting state," and the nearest at or before as the "prior state," so the judge sees before/after.

Rationale: Reading from history (the durable, ordered record) keeps the judge reproducible and decoupled from live session lifetimes — a game can be evaluated long after it ends. It reuses the existing read APIs rather than re-instrumenting producers.

Alternatives considered: (a) Pull live game state from game-service at eval time — rejected: the live session may be gone or advanced; the judge must grade the state *as it was* at that move, which only the recorded event preserves. (b) Have producers push a pre-assembled "judge bundle" — rejected: duplicates payload already captured in history and couples producers to the judge's input shape.

### 5. Per-round trigger: detect round boundaries from `game-service` state, evaluate the round on close

Round-level evaluation grades a whole turn/round, not a single move. The eval-service detects round boundaries from the `game-service` state events: each state payload exposes the current round/phase (DragnCards owns round/phase logic), so a **round change** between consecutive state events signals that the prior round closed. When a round closes at `seq R`, the eval-service evaluates the round spanning the moves from the prior round boundary up to `R`, emitting one `evaluator` event with `scope = round` targeting `R` (the closing `seq`). The first round opens at the game's first event and closes at the first observed round change; the final round closes on a terminal game status (`win`/`loss`).

Rationale: Rounds are a property of game state that DragnCards already tracks, so deriving boundaries from state events needs no new signal and stays robust to however the agent sequences its moves within a round. Targeting the closing `seq` keeps round verdicts `seq`-correlated and idempotent under Decision 3 (`scope = round`).

Alternatives considered: (a) A dedicated "round-end" event emitted by game-service — rejected: requires a producer change and bakes round semantics into game-service emission; deriving from the state field is additive-free on producers. (b) Fixed-N-moves windows — rejected: not aligned with actual game rounds, so verdicts would be hard to interpret. Risk: if a game ends without a clean final round-change signal, the terminal-status fallback closes the last round; if upstream changes how round/phase is represented in state, boundary detection must follow it (mitigated by reading the documented state field and surfacing "round boundary undetected" rather than guessing).

### 6. The judge LLM: isolated fresh session via Bifrost, strong evaluation prompt, may reuse MC rules skills

Each evaluation runs in a **fresh, stateless judge invocation** — the judge never shares or mutates the game-playing agent's session/context. The eval-service builds a self-contained judge prompt containing: the evaluation rubric (per-criterion definitions and scoring scale), the assembled inputs from Decision 4/5 (state, move(s), the agent's stated reasoning), and an instruction to return a structured verdict (per-criterion scores, overall score, rationale, optional flags). The judge call goes through the Bifrost gateway exactly like orchestrator calls (see the `claude-api` skill / Bifrost contract for the request shape), so any configured model/provider works; the default model/provider are configurable via env. The judge prompt MAY reuse the existing Marvel Champions rules skills (the same `skills/` content the orchestrator loads) so rules-legality grading is grounded in the actual ruleset, kept model-agnostic.

Rationale: A fresh session is what "evaluate in isolation" means — the judge must not be primed by the agent's own conversation beyond the explicitly supplied reasoning it is grading. Routing through Bifrost reuses the existing gateway, retry metadata, and observability. Reusing rules skills avoids duplicating the ruleset and keeps legality judgments accurate.

Alternatives considered: (a) Resume the agent's session and ask it to self-grade — rejected: self-grading is biased and not isolated; it also re-enters live session storage. (b) Hard-code a single provider/model — rejected: violates "model/provider configurable" and prevents comparing judges. (c) Call provider SDKs directly — rejected: the repo standard is all LLM traffic through Bifrost (budget, identity, observability live there).

### 7. Dedicated Bifrost virtual key/provider entry for the judge (budget + identity isolation)

The judge uses a **dedicated Bifrost identity** — a separate virtual key / provider key entry (e.g. an `eval-judge` key in `services/bifrost/config.json`, env-backed like the others) distinct from the game-playing keys. The eval-service is configured to send judge traffic under that identity. This gives the judge its own budget/rate limits and makes judge traffic recognizable as non-game traffic in gateway logs/metrics.

Rationale: Budget isolation prevents judge spend from competing with or masking game-play spend, and a distinct identity makes cost attribution and rate-limit policy per-purpose. It also lets operators throttle or disable the judge independently without touching game play.

Alternatives considered: (a) Reuse the game-playing key with a tag/metadata field — rejected: shared budget and rate limits, and harder to attribute spend; a runaway judge could starve live play. (b) A separate Bifrost instance for the judge — rejected: operational overhead far beyond what a distinct key/provider entry needs; revisit only if isolation at the key level proves insufficient.

### 8. The `evaluator` event written back to history (payload schema + actor extension)

Verdicts are written back through the existing history-service HTTP ingest endpoint `POST /games/{game_id}/events` as an envelope with **actor `evaluator`** and `event_type` such as `move_evaluation` / `round_evaluation`. Because the current envelope rejects any actor other than `agent | game-service`, this change extends the allowed actor set to include `evaluator` (captured as a `history-event-store` delta). The payload schema:

```
{
  "scope": "move" | "round",
  "target_seq": <int>,                 // the move's seq, or the round's closing seq
  "round_span": { "from_seq": <int>, "to_seq": <int> } | null,   // present for round scope
  "scores": {                          // per-criterion, 0-10 scale
    "rules_legality": <number>,        // 0-10
    "strategic_quality": <number>,     // 0-10
    "tempo_efficiency": <number>,      // 0-10
    "threat_resource": <number>        // 0-10 (threat/resource management)
    // additional criteria may be added forward-compatibly
  },
  "overall_score": <number>,           // 0-10
  "rationale": "<judge explanation>",
  "flags": ["illegal_move", ...] | [],
  "evaluator": { "model": "<id>", "provider": "<id>", "evaluator_version": "<str>" }
}
```

History assigns this event its own `seq` and `recorded_at`; the verdict points back at the graded move/round via `target_seq` (and `round_span`). The write uses `idempotency_key = hash(game_id, target_seq, scope, evaluator_version)` so a duplicate write-back is stored once.

Rationale: Writing back via the existing HTTP ingest endpoint reuses the durable, idempotent, ordered store with no new persistence path, and puts verdicts on the same timeline as moves so the UI and any future analytics get them for free. Extending the actor set (rather than overloading `agent`/`game-service`) keeps verdicts cleanly distinguishable in storage, restore-replay filtering (evaluator events, like agent events, are never replayed as game mutations), and the UI.

Alternatives considered: (a) Store verdicts only in eval-service's own PostgreSQL — rejected: they would not appear on the shared timeline and the UI/analytics would need a second source; the product decision is verdicts on the same timeline. (b) Reuse actor `agent` for verdicts — rejected: conflates the player with the judge and would mis-color the timeline and any replay filter.

### 9. Failure isolation and cost controls: retry-then-skip, never block ingestion or play

The eval-service is strictly downstream and side-effecting only via history write-back. If the judge call fails (provider error, timeout, rate limit) the eval-service retries with bounded backoff up to a configurable attempt limit; if it still fails it **skips** that target — recording a skip/`error` outcome in its bookkeeping and `XACK`ing the stream entry (or moving it to a dead-letter list) — and continues. It never holds back, fails, or slows history ingestion or game play, because it is a separate consumer reading a copy of committed events; history has already durably stored everything before publishing to `eval:ingest`. Cost controls: per-game and global concurrency caps on judge calls, an optional sampling/rate knob (e.g. evaluate every move vs every Nth move vs round-only), the dedicated Bifrost budget (Decision 7), and a configurable max judge token budget per evaluation.

Rationale: The judge is best-effort quality signal, not a correctness gate; the durable record exists with or without it. Bounded retry handles transient provider issues; skip-and-continue preserves throughput and avoids a poison message stalling the queue. Cost controls keep an automatic per-event LLM call affordable.

Alternatives considered: (a) Unbounded retry — rejected: a persistently failing target would block the consumer and burn budget. (b) Block/ack-with-requeue forever — rejected: same poison-message stall. (c) No sampling, always per-move — kept as the default but made configurable so cost can be tuned without code change.

### 10. Cloud-native: stateless, horizontally scalable, optional dedicated PostgreSQL

The eval-service holds no state in memory: consumer offsets live in the Valkey stream consumer group; idempotency/bookkeeping (evaluated-target keys, skip records, attempt counts) live in a dedicated PostgreSQL (kept separate from history's and orchestrator's databases, matching the isolation precedent). Multiple replicas share one consumer group; the unique evaluated-target constraint guarantees at-most-once evaluation regardless of which replica processes a message. Health/readiness endpoints report API, PostgreSQL, Valkey, history-service reachability, and Bifrost reachability without exposing secrets; all secrets are env-externalized.

Alternatives considered: (a) No database, dedupe only via Valkey keys — rejected: Valkey is ephemeral; an eviction/restart could lose the at-most-once guarantee and re-spend budget. A durable evaluated-target record is the safe dedupe substrate. (b) Reuse history's PostgreSQL — rejected: mixes failure domains and write patterns, violating the per-service isolation precedent.

## Risks / Trade-offs

- **Per-event LLM cost** — an automatic judge call per move can be expensive at volume. Mitigated by the dedicated Bifrost budget, configurable sampling/round-only mode, concurrency caps, and a per-evaluation token budget (Decision 9).
- **Round-boundary detection depends on the game-state representation** (round/phase field) which originates upstream in DragnCards and is uncontrolled. Mitigated by reading the documented state field, falling back to terminal status for the final round, and surfacing "boundary undetected" rather than emitting a wrong-span verdict (Decision 5).
- **At-least-once duplicates / concurrent replicas** — mitigated by the durable `(game_id, target_seq, scope)` evaluated-target constraint and the write-back `idempotency_key` (Decisions 3, 8).
- **Shared envelope/actor contract across services** — extending the allowed actor set to `evaluator` is a contract change to history-event-store; mitigated by the existing forward-compatible-unknown-fields rule and by versioning the verdict payload (additional criteria added forward-compatibly).
- **Judge quality/consistency** — an LLM judge can be noisy or biased. Mitigated by a structured rubric, a recorded `evaluator_version` so prompt/model changes are traceable, and keeping verdicts advisory (no live feedback loop). Improving rubric quality is iterative and out of scope to "solve."
- **Eval-service backlog if the judge is slow** — the `eval:ingest` stream is bounded by `MAXLEN`; history's durable record is the source of truth, so a backlog at worst delays/loses *evaluations*, never game data. A consumer-lag signal (via observability) alerts operators.
- **Judge call failure must never block ingestion/play** — guaranteed structurally because the judge reads a *copy* of already-committed events and writes back only advisory events (Decision 9).

## Migration Plan

1. Scaffold `services/eval-service/` (FastAPI app, settings, health/readiness, Dockerfile, optional dedicated PostgreSQL).
2. Add the `evaluator` actor to the history-event-store envelope and the post-commit publish to `eval:ingest` (additive to history-service).
3. Add the eval-service Valkey-stream consumer group, idempotent evaluated-target bookkeeping, and judge-input assembly from the history read API.
4. Add the dedicated `eval-judge` Bifrost virtual key/provider entry and route judge calls through it; implement per-move evaluation and the structured verdict.
5. Add per-round boundary detection and round evaluation.
6. Add evaluator-event write-back via the history HTTP ingest endpoint with the verdict idempotency key.
7. Add failure isolation (retry-then-skip / dead-letter), cost controls (sampling, concurrency, token budget), and the consumer-lag signal.
8. Add the dashboard timeline rendering of evaluator events/scores.
9. Wire Docker Compose (service + database + Bifrost judge identity) and run integration tests.

Rollback is removal of the new service, its database, compose entries, the Bifrost judge key, and the two additive history-service hooks (the publish and the actor allow-list entry). Existing services keep working unchanged because the history publish is additive and the eval-service is a decoupled downstream consumer.

## Resolved Decisions

Confirmed with the product owner; reflected above:

- **Scoring scale and criteria:** overall **0-10** plus four per-criterion 0-10 scores — `rules_legality`, `strategic_quality`, `tempo_efficiency`, `threat_resource` — plus a text rationale and optional flags. Additional criteria may be added forward-compatibly.
- **Trigger:** **user-directed, on-demand** — the user selects which game/turns/moves (or whole game) to evaluate via a request API; there is no automatic per-event evaluation (the auto queue is a deferred future mode). Per-move and per-round are both selectable units.
- **Judge model/provider:** **no hard default** — the `eval-judge` identity requires an explicit `EVAL_JUDGE_MODEL` (and provider) setting; the service refuses to start / skips with a clear error if unset. This forces a deliberate model+budget choice.
- **Re-evaluation policy:** **version-tag only** — every evaluator event carries `evaluator_version`; new evaluations use the current version and existing verdicts are left intact. Bulk re-grading on a version bump is a deliberate future change (a manual/admin trigger), explicitly out of scope here.
