## ADDED Requirements

### Requirement: Evaluation service boundary and persistence
The system SHALL provide a dedicated `eval-service` (Python/FastAPI) that evaluates how well the game-playing agent played by judging recorded moves and rounds on user request, and SHALL NOT retain evaluation state in process memory; durable evaluation requests, idempotency, and bookkeeping data SHALL live in a dedicated PostgreSQL database not shared with other services.

#### Scenario: Eval-service uses dedicated isolated storage
- **WHEN** the eval-service records that a target has been evaluated
- **THEN** the eval-service SHALL persist that record in its dedicated PostgreSQL database and SHALL NOT keep evaluation bookkeeping only in process memory

#### Scenario: Health and readiness without secrets
- **WHEN** a client requests the eval-service health or readiness endpoint
- **THEN** the eval-service SHALL report API, PostgreSQL, history-service, and Bifrost readiness and SHALL NOT expose any secret values

### Requirement: On-demand evaluation of user-selected targets
The eval-service SHALL expose an API for a user to request evaluation of explicitly selected targets within a game — one or more moves (by `seq`), one or more rounds, a `seq` range, and/or the whole game — and SHALL evaluate only the requested targets, reading the events it needs from the history-service. The eval-service SHALL NOT automatically evaluate moves or rounds that were not requested.

#### Scenario: Request evaluation of selected targets
- **WHEN** a user submits an evaluation request for a `game_id` naming specific move `seq`s, round(s), a `seq` range, or the whole game
- **THEN** the eval-service SHALL evaluate only the requested targets, reading their events from the history-service, and SHALL NOT evaluate unrequested moves or rounds

#### Scenario: No automatic evaluation without a request
- **WHEN** a move or round is recorded in the history event store but no evaluation has been requested for it
- **THEN** the eval-service SHALL NOT evaluate it

#### Scenario: Report evaluation request status and results
- **WHEN** a user queries the status of a submitted evaluation request
- **THEN** the eval-service SHALL report which requested targets are pending, completed, skipped, or failed, SHALL expose the resulting verdicts, and SHALL aggregate an overall request status of `pending` (any target non-terminal), `completed` (all succeeded), `failed` (terminal but none succeeded), or `partial` (a mix of succeeded and skipped/failed)

### Requirement: Idempotent evaluation with explicit re-evaluation
The eval-service SHALL evaluate each target at most once by default, deduplicating on `(game_id, target_seq, scope)` where `scope` is `move` or `round`, using a durable claim so that repeated requests and concurrent workers do not produce a second judge call for the same target — UNLESS the user explicitly requests re-evaluation (force), in which case a fresh verdict SHALL be produced.

#### Scenario: Repeated request is not re-evaluated by default
- **WHEN** a target `(game_id, target_seq, scope)` that already has a verdict is requested again without the force option
- **THEN** the eval-service SHALL NOT issue a second judge call and SHALL return the existing verdict

#### Scenario: Explicit re-evaluation produces a fresh verdict
- **WHEN** a user requests evaluation of an already-evaluated target with the force/re-evaluate option
- **THEN** the eval-service SHALL issue a new judge call and write a fresh verdict event

#### Scenario: Concurrent claims resolve to a single evaluation
- **WHEN** two workers attempt to evaluate the same `(game_id, target_seq, scope)` concurrently
- **THEN** exactly one SHALL win the durable claim and perform the evaluation and the other SHALL treat the target as already claimed

### Requirement: Per-move evaluation
The eval-service SHALL evaluate each agent move in isolation, assembling the judge's input from the recorded `agent` move event (the intended action, the agent's reasoning/context, and the action arguments) correlated with the `game-service` state for that move, read from the history-service.

#### Scenario: Evaluate a recorded agent move
- **WHEN** the eval-service processes an `agent` move event target for a `game_id` and `target_seq`
- **THEN** the eval-service SHALL assemble the move, the agent's reasoning/context, and the correlated game state from history and SHALL produce a `scope=move` verdict targeting that move's `seq`

#### Scenario: Judge input includes the agent's reasoning
- **WHEN** the eval-service assembles the input for a per-move evaluation
- **THEN** the input SHALL include the playing agent's reasoning/context for that move so the judge can critique the decision and its rationale

### Requirement: Per-round evaluation
The eval-service SHALL evaluate each round/turn in isolation, detecting round boundaries from the round/phase information on `game-service` state events, closing the final round on a terminal game status, and producing one round verdict per closed round.

#### Scenario: Evaluate a closed round
- **WHEN** the eval-service detects that a round has closed at a `game-service` state event with `seq` R
- **THEN** the eval-service SHALL assemble the round's moves and produce a `scope=round` verdict targeting `seq` R with the round's `from_seq`/`to_seq` span

#### Scenario: Final round closed by terminal status
- **WHEN** a game reaches a terminal status (`win` or `loss`) without a subsequent round-change signal
- **THEN** the eval-service SHALL close the final round at that terminal event and produce its round verdict

### Requirement: Isolated judge LLM under a dedicated Bifrost identity
The eval-service SHALL run each evaluation through a fresh, stateless judge LLM invocation routed through the Bifrost gateway under a dedicated Bifrost virtual key/provider identity that is separate from the game-playing identities. The judge model and provider SHALL be operator-configured with NO built-in default; the eval-service SHALL refuse to perform an evaluation when no judge model is configured. The judge SHALL NOT reuse or mutate the game-playing agent's session.

#### Scenario: Judge runs in a fresh isolated session
- **WHEN** the eval-service invokes the judge for a target
- **THEN** the judge invocation SHALL be a fresh session containing only the evaluation prompt and assembled inputs and SHALL NOT reuse the game-playing agent's session or context

#### Scenario: Judge traffic uses the dedicated Bifrost identity
- **WHEN** the eval-service sends a judge request through Bifrost
- **THEN** the request SHALL be sent under the dedicated judge virtual key/provider identity and SHALL NOT use a game-playing identity

#### Scenario: Judge model and provider are configurable
- **WHEN** an operator configures the eval-service judge model and provider
- **THEN** the eval-service SHALL route judge requests to that configured model and provider through Bifrost without code changes

#### Scenario: No judge model configured
- **WHEN** the eval-service is asked to evaluate a target but no judge model has been configured
- **THEN** the eval-service SHALL NOT invoke a default model and SHALL skip the evaluation with a clear configuration error rather than guessing a model

### Requirement: Structured verdict written back as an evaluator event
The eval-service SHALL write each evaluation verdict back to the history-service through its HTTP ingest endpoint as a versioned event envelope with actor `evaluator`, whose payload contains an overall 0-10 score, four per-criterion 0-10 scores (`rules_legality`, `strategic_quality`, `tempo_efficiency`, `threat_resource`), a rationale, the evaluation scope, the `evaluator_version`, and the target move `seq` or round span it grades, using an idempotency key derived from `(game_id, target_seq, scope, evaluator_version)`.

#### Scenario: Verdict ingested as an evaluator event
- **WHEN** the eval-service completes a verdict for a `game_id` and `target_seq`
- **THEN** the eval-service SHALL submit it to the history-service HTTP ingest endpoint as an envelope with actor `evaluator` whose payload includes the per-criterion scores, the overall score, the rationale, the scope, and the target reference

#### Scenario: Verdict references the graded move or round
- **WHEN** the eval-service writes a verdict
- **THEN** the payload SHALL identify the graded target by `target_seq` for a move and additionally by the round span for a round, so it is `seq`-correlated to the move/round on the same game timeline

#### Scenario: Duplicate verdict write-back stored once
- **WHEN** the same verdict for a `(game_id, target_seq, scope, evaluator_version)` is written back more than once
- **THEN** the history-service SHALL store it exactly once because the verdict carries a stable idempotency key

### Requirement: Failure isolation from ingestion and play
The eval-service SHALL never block, fail, or slow history ingestion or game play. When a judge call fails or times out, the eval-service SHALL retry up to a configured attempt limit and then skip the target, recording the skip outcome and acknowledging or dead-lettering the queue entry, so that a failing target does not stall the queue.

#### Scenario: Judge failure results in a skipped target
- **WHEN** a judge call for a target fails repeatedly up to the configured attempt limit
- **THEN** the eval-service SHALL skip that target, record the skip/error outcome, and continue processing subsequent targets without stalling the queue

#### Scenario: Ingestion and play unaffected by judge outage
- **WHEN** the judge is unavailable while games continue to be played and recorded
- **THEN** history ingestion and game play SHALL proceed unaffected because the eval-service consumes a copy of already-committed events and only writes advisory evaluator events

### Requirement: Evaluation cost controls
The eval-service SHALL provide configurable cost controls including an evaluation sampling mode (per-move, every-Nth-move, or round-only), per-game and global judge concurrency caps, and a per-evaluation judge token budget, so that automatic per-event evaluation cost can be tuned without code changes.

#### Scenario: Sampling mode limits evaluated moves
- **WHEN** the eval-service is configured with a round-only or every-Nth-move sampling mode
- **THEN** the eval-service SHALL evaluate only the targets selected by that mode and SHALL NOT issue judge calls for the skipped moves

#### Scenario: Concurrency cap bounds in-flight judge calls
- **WHEN** the number of in-flight judge calls reaches the configured concurrency cap
- **THEN** the eval-service SHALL defer additional judge calls until capacity is available rather than exceeding the cap

#### Scenario: Per-request target cap bounds total enqueued work
- **WHEN** a selection (`whole_game`, a wide `seq_range`, or a large `seqs` list) expands to more targets than the configured per-request limit
- **THEN** the eval-service SHALL reject the request with HTTP 400 and SHALL NOT enqueue any targets, so a single request cannot amplify total judge cost beyond the limit

### Requirement: Exclusive target claims and round resolution

The eval-service SHALL evaluate each claimed target at most once even when multiple worker replicas drain concurrently, and SHALL resolve a round-scope target from any sequence contained within a round.

#### Scenario: Concurrent replicas evaluate each target once
- **WHEN** two worker replicas drain the same pending targets concurrently
- **THEN** each target SHALL be claimed by exactly one replica (atomic `pending` -> `running` transition) and SHALL produce at most one verdict

#### Scenario: Force re-claim is atomic with an in-flight worker
- **WHEN** a `force` re-evaluation resets a target while a worker is mid-evaluation on it
- **THEN** the conflict check and reset SHALL occur in one transaction and the in-flight worker's terminal write SHALL be discarded (conditional on the row still being `running`), so the fresh evaluation is the one that stands

#### Scenario: Round scope resolves a mid-round sequence
- **WHEN** a round-scope request selects a sequence that falls inside a detected round span but is not the round-closing sequence
- **THEN** the eval-service SHALL evaluate the round that contains that sequence, and SHALL only error when the sequence is outside every detectable round
