# agent-move-evaluation Specification

## Purpose
Judge how well the game-playing agent actually played, so that play quality is measurable rather
than a matter of impression. A dedicated `eval-service` replays recorded moves and rounds from the
history event store on request, hands each one to a judge LLM under its own provider identity, and
persists the verdicts durably — separating "what happened in the game" (owned by
`history-event-store`) from "how good was it" (owned here). Evaluation is user-initiated and
asynchronous: it never sits on the path of a live game, and it never keeps request, idempotency, or
verdict state in process memory.
## Requirements
### Requirement: Evaluation service boundary and persistence
The system SHALL provide a dedicated `eval-service` (Python/FastAPI) that evaluates how well the game-playing agent played by judging recorded moves and rounds on user request, and SHALL NOT retain evaluation state in process memory; durable evaluation requests, idempotency, and bookkeeping data SHALL live in a dedicated PostgreSQL database not shared with other services.

The eval-service container image SHALL start cleanly regardless of the module's on-disk depth, and SHALL package the shared rules-skill directory so that skill names selected for a judge configuration resolve to skill content inside the container.

#### Scenario: Eval-service uses dedicated isolated storage
- **WHEN** the eval-service records that a target has been evaluated
- **THEN** the eval-service SHALL persist that record in its dedicated PostgreSQL database and SHALL NOT keep evaluation bookkeeping only in process memory

#### Scenario: Health and readiness without secrets
- **WHEN** a client requests the eval-service health or readiness endpoint
- **THEN** the eval-service SHALL report API, PostgreSQL, history-service, and Bifrost readiness, plus whether a judge model and a dedicated judge key for its provider are configured, and SHALL NOT expose any secret values

#### Scenario: Packaged service boots and resolves skills
- **WHEN** the eval-service container image starts
- **THEN** the service SHALL boot to a healthy state without an import-time error, and SHALL resolve rules-skill names against a skills directory packaged into the image at the configured skill root

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
The eval-service SHALL evaluate each target at most once by default, deduplicating on `(game_id, target_seq, scope)` where `scope` is `move` or `round`, using a durable claim so that repeated requests and concurrent workers do not produce a second judge call for the same target — UNLESS the user explicitly requests re-evaluation (force), in which case a fresh verdict SHALL be produced. When a force re-evaluation resets a target that is still being evaluated, the eval-service SHALL cancel the in-flight evaluation before a fresh one starts, so at most one evaluation of a target is ever in flight and no stale verdict is written alongside the fresh one.

#### Scenario: Repeated request is not re-evaluated by default
- **WHEN** a target `(game_id, target_seq, scope)` that already has a verdict is requested again without the force option
- **THEN** the eval-service SHALL NOT issue a second judge call and SHALL return the existing verdict

#### Scenario: Explicit re-evaluation produces a fresh verdict
- **WHEN** a user requests evaluation of an already-evaluated target with the force/re-evaluate option
- **THEN** the eval-service SHALL issue a new judge call and write a fresh verdict event

#### Scenario: Concurrent claims resolve to a single evaluation
- **WHEN** two workers attempt to evaluate the same `(game_id, target_seq, scope)` concurrently
- **THEN** exactly one SHALL win the durable claim and perform the evaluation and the other SHALL treat the target as already claimed

#### Scenario: Force re-claim during a running evaluation writes a single verdict
- **WHEN** a force re-evaluation resets a target from `running` back to `pending` while a worker is still mid-evaluation on that same target (already past the `running` re-check)
- **THEN** the eval-service SHALL cancel the in-flight task so that exactly one verdict is written to history for that target — the fresh evaluation's verdict — and the stale evaluation's write-back SHALL NOT be committed

#### Scenario: Force re-claim keeps the fresh task cancellable
- **WHEN** a stale evaluation task finishes its cleanup after a force re-claim has registered a new in-flight task for the same target
- **THEN** the stale task's cleanup SHALL NOT evict the newer task from the in-flight registry, so the fresh task remains cancellable

### Requirement: Per-move evaluation
The eval-service SHALL evaluate each agent move in the context of the round it belongs to — NOT as an isolated action — assembling the judge's input from the recorded `agent` move event (the intended action, the agent's reasoning/context, and the action arguments) correlated with the `game-service` state for that move and with the other agent moves of that move's round, all read from the history-service. The verdict SHALL remain scoped to the single move; the round supplies the context in which that move is judged.

#### Scenario: Evaluate a recorded agent move
- **WHEN** the eval-service processes an `agent` move event target for a `game_id` and `target_seq`
- **THEN** the eval-service SHALL assemble the move, the agent's reasoning/context, the correlated game state, and the move's round context from history, and SHALL produce a `scope=move` verdict targeting that move's `seq`

#### Scenario: Judge input includes the agent's reasoning
- **WHEN** the eval-service assembles the input for a per-move evaluation
- **THEN** the input SHALL include the playing agent's reasoning/context for that move so the judge can critique the decision and its rationale

#### Scenario: A move is not graded as though it stood alone
- **WHEN** the eval-service assembles the input for a move that is one call of a multi-call play, such as exhausting a character to pay for an ability whose effect a later call applies
- **THEN** the input SHALL identify the round the move belongs to and SHALL present the round's other moves as the play the graded move is part of

### Requirement: Per-round evaluation
The eval-service SHALL evaluate each round/turn in isolation, detecting round boundaries from the round/phase information on `game-service` state events, closing the final round on a terminal game status, and producing one round verdict per closed round.

Because a `game-service` event embeds the state **after** its action was applied, the event whose state first reports a different round number is the event that CLOSED the preceding round. That event SHALL be the closing sequence (`to_seq`) of the round it closed, and the next round SHALL start at the sequence after it — so a round's span covers the move that ended it, and a round roll-up is graded against the board as that round ended rather than the board from before its own closing action. This SHALL match how the history transcript attributes a `game-service` event, so an evaluated round span and a displayed round band cover the same events. An event that both closes a round and carries a terminal status SHALL close that round exactly once and SHALL NOT open an additional empty span after itself.

Every round number the eval-service reports or accepts SHALL be the 1-based round of PLAY, which is the recorded `roundNumber` plus one, because DragnCards `roundNumber` counts COMPLETED rounds and reads 0 throughout the first round of play. The round named in a round-level judge prompt and the round numbers accepted in a request's round selection SHALL both use that convention, so a round names the same round the history transcript names. The raw counter SHALL NOT be presented to a judge or a user.

#### Scenario: Evaluate a closed round
- **WHEN** the eval-service detects that a round has closed at a `game-service` state event with `seq` R
- **THEN** the eval-service SHALL assemble the round's moves and produce a `scope=round` verdict targeting `seq` R with the round's `from_seq`/`to_seq` span

#### Scenario: A round ends at the event that closed it
- **WHEN** a `game-service` event's post-action state is the first to report a new round number, at `seq` R, and the preceding round began at `seq` F
- **THEN** that round's span SHALL be `F` to `R` inclusive, and the next round SHALL begin at `seq` R+1, rather than the round ending at `seq` R-1 and the next round beginning at `seq` R

#### Scenario: The move that closed a round is graded inside that round
- **WHEN** an agent move advances the game out of a round and the resulting state event reports the new round number
- **THEN** that move SHALL be part of the span of the round it closed, and the round's closing state SHALL be the state recorded at the round's closing sequence

#### Scenario: The first round of play is round 1, not round 0
- **WHEN** a round's `game-service` state events report `roundNumber` 0 (DragnCards has not yet counted a completed round)
- **THEN** the eval-service SHALL report that round as round 1 — in the round-level judge prompt and in the round numbers it accepts in a selection — and SHALL NOT name it round 0

#### Scenario: A selected round number means the round of play
- **WHEN** an evaluation request selects rounds by number
- **THEN** the eval-service SHALL resolve each number as the round of play of that ordinal (1 being the first round played), matching the numbering the history transcript displays

#### Scenario: Final round closed by terminal status
- **WHEN** a game reaches a terminal status (`win` or `loss`) without a subsequent round-change signal
- **THEN** the eval-service SHALL close the final round at that terminal event and produce its round verdict

#### Scenario: Round change and terminal status on the same event
- **WHEN** the event that closes a round is also the event carrying the terminal game status
- **THEN** the eval-service SHALL close that round once at that event and SHALL NOT emit a further round whose span starts after its own closing sequence

### Requirement: Isolated judge LLM under a dedicated Bifrost identity
The eval-service SHALL run each evaluation through a fresh, stateless judge LLM invocation routed through the Bifrost gateway under a dedicated judge key that is separate from the game-playing keys, for WHICHEVER provider the configured judge model routes to. The judge model and provider SHALL be operator-configured with NO built-in default; the eval-service SHALL refuse to perform an evaluation when no judge model is configured. The judge SHALL NOT reuse or mutate the game-playing agent's session.

The eval-service SHALL address the judge key by an operator-configurable NAME, sent as the gateway's named-key selection header, so a single setting pins the judge identity across every provider. The eval-service SHALL NOT rely on the gateway authorization bearer to select a provider key. Judge traffic SHALL NOT fall back to a game-playing key implicitly; where an operator deliberately disables named-key selection, the service SHALL log that at startup and report it in readiness.

#### Scenario: Judge runs in a fresh isolated session
- **WHEN** the eval-service invokes the judge for a target
- **THEN** the judge invocation SHALL be a fresh session containing only the evaluation prompt and assembled inputs and SHALL NOT reuse the game-playing agent's session or context

#### Scenario: Judge traffic uses the dedicated Bifrost identity
- **WHEN** the eval-service sends a judge request through Bifrost
- **THEN** the request SHALL name the dedicated judge key so the gateway selects it for the target provider, and SHALL NOT use a game-playing identity

#### Scenario: Judge identity holds for any provider
- **WHEN** the configured judge model routes to a provider other than the default one
- **THEN** the same named judge key SHALL be selected for that provider, so the judge uses that provider's own judge credential rather than its game-playing key, with no code change

#### Scenario: Judge model and provider are configurable
- **WHEN** an operator configures the eval-service judge model and provider
- **THEN** the eval-service SHALL route judge requests to that configured model and provider through Bifrost without code changes

#### Scenario: No judge model configured
- **WHEN** the eval-service is asked to evaluate a target but no judge model has been configured
- **THEN** the eval-service SHALL NOT invoke a default model and SHALL skip the evaluation with a clear configuration error rather than guessing a model

#### Scenario: Missing judge key is reported, not absorbed
- **WHEN** the judge provider has no dedicated judge key configured
- **THEN** readiness SHALL report the judge key as missing for that provider and SHALL report status `degraded`
- **AND** an attempted evaluation SHALL be recorded against the target with the gateway's own error identifying the missing key and provider, rather than a generic judge failure

### Requirement: Structured verdict written back as an evaluator event
The eval-service SHALL write each evaluation verdict back to the history-service through its HTTP ingest endpoint as a versioned event envelope with actor `evaluator`, whose payload contains an overall 0-10 score, four per-criterion 0-10 scores (`rules_legality`, `strategic_quality`, `tempo_efficiency`, `threat_resource`), a rationale, the evaluation scope, the `evaluator_version`, and the target move `seq` or round span it grades, using an idempotency key derived from `(game_id, target_seq, scope, evaluator_version)`.

A round-scoped verdict SHALL additionally carry the **round of play** it grades as its own payload field, distinct from its sequence span. The span identifies the verdict's position on the timeline and is a pair of event sequence numbers; the round of play is the 1-based ordinal the history transcript and the round listing name that round by (the recorded `roundNumber` plus one). A consumer SHALL therefore never have to derive one from the other, and the round a verdict grades SHALL be readable from the verdict alone rather than re-derived from boundaries detected elsewhere. Scopes that do not grade a single round — a move, which is named by its own sequence, and a whole game, which spans every round — SHALL leave the round of play unset rather than reporting a misleading one.

A change to HOW the eval-service derives what a verdict grades — including how round spans are detected and numbered — SHALL be surfaced by a change to `evaluator_version`, so verdicts produced under different derivations are distinguishable in recorded history rather than presented as comparable. Verdicts already recorded SHALL NOT be rewritten, re-scored, or deleted by such a change; re-grading SHALL remain an explicit user-requested re-evaluation. Recording an additional descriptive field about what a verdict already graded — one that changes neither the judge's prompt, the graded span, nor the score scale — SHALL NOT change `evaluator_version`, because that would declare verdicts on the same scale to be incomparable.

#### Scenario: Verdict ingested as an evaluator event
- **WHEN** the eval-service completes a verdict for a `game_id` and `target_seq`
- **THEN** the eval-service SHALL submit it to the history-service HTTP ingest endpoint as an envelope with actor `evaluator` whose payload includes the per-criterion scores, the overall score, the rationale, the scope, and the target reference

#### Scenario: Verdict references the graded move or round
- **WHEN** the eval-service writes a verdict
- **THEN** the payload SHALL identify the graded target by `target_seq` for a move and additionally by the round span for a round, so it is `seq`-correlated to the move/round on the same game timeline

#### Scenario: A round verdict names the round of play it graded
- **WHEN** the eval-service writes a round-scoped verdict for a round whose events run from sequence F to sequence T
- **THEN** the payload SHALL carry the round's 1-based round of play as a field of its own alongside the `F`–`T` sequence span, so the round can be named from the verdict without re-detecting boundaries

#### Scenario: Move and game verdicts carry no round of play
- **WHEN** the eval-service writes a move-scoped or game-scoped verdict
- **THEN** the payload SHALL leave the round of play unset, because a move is identified by its own sequence and a game verdict covers every round

#### Scenario: Duplicate verdict write-back stored once
- **WHEN** the same verdict for a `(game_id, target_seq, scope, evaluator_version)` is written back more than once
- **THEN** the history-service SHALL store it exactly once because the verdict carries a stable idempotency key

#### Scenario: A change in span derivation is not applied silently
- **WHEN** the eval-service changes how a round's span is derived, so a new round verdict grades a different span from an older verdict of the same round
- **THEN** the new verdicts SHALL carry a different `evaluator_version` from the older ones, and the older verdicts SHALL remain in history exactly as recorded

#### Scenario: Describing an already-graded verdict does not break comparability
- **WHEN** the eval-service adds a payload field that describes what a verdict graded without changing the judge's prompt, the graded span, or the score scale
- **THEN** `evaluator_version` SHALL stay as it is, and verdicts recorded before the field was added SHALL remain comparable to those recorded after it

### Requirement: Failure isolation from ingestion and play
The eval-service SHALL never block, fail, or slow history ingestion or game play. When a judge call fails or times out, the eval-service SHALL retry up to a configured attempt limit and then record the target as `failed` carrying the reason, acknowledging or dead-lettering the queue entry, so that a failing target does not stall the queue.

A failure SHALL NOT be recorded as `skipped`. `skipped` SHALL mean only that the target carried no decision a judge could grade, so a client can always distinguish an error from a deliberate skip. Every error path — judge attempts exhausted, an assembly error, an undetectable round boundary, an unreadable recorded timeline, a failed verdict write-back, and no configured judge model — SHALL record `failed` with its reason.

#### Scenario: Judge failure results in a failed target with its reason
- **WHEN** a judge call for a target fails repeatedly up to the configured attempt limit
- **THEN** the eval-service SHALL record that target as `failed` carrying the reason for the failure, SHALL NOT write a verdict for it, and SHALL continue processing subsequent targets without stalling the queue

#### Scenario: An error is never reported as a skip
- **WHEN** a target fails for any reason — the judge, assembly, round-boundary detection, the history read, the verdict write-back, or a missing judge model
- **THEN** its terminal status SHALL be `failed` and SHALL NOT be `skipped`, so it cannot be confused with a deliberately skipped non-strategic action

#### Scenario: Ingestion and play unaffected by judge outage
- **WHEN** the judge is unavailable while games continue to be played and recorded
- **THEN** history ingestion and game play SHALL proceed unaffected because the eval-service consumes a copy of already-committed events and only writes advisory evaluator events

### Requirement: Evaluation cost controls
The eval-service SHALL provide configurable cost controls including an evaluation sampling mode (per-move, every-Nth-move, or round-only), per-game and global judge concurrency caps, and a per-evaluation judge token budget, so that automatic per-event evaluation cost can be tuned without code changes. The concurrency caps SHALL be enforced from durable state rather than from process-local memory, so that a restart or a second worker replica cannot exceed them.

#### Scenario: Sampling mode limits evaluated moves
- **WHEN** the eval-service is configured with a round-only or every-Nth-move sampling mode
- **THEN** the eval-service SHALL evaluate only the targets selected by that mode and SHALL NOT issue judge calls for the skipped moves

#### Scenario: Concurrency cap bounds in-flight judge calls
- **WHEN** the number of in-flight judge calls reaches the configured concurrency cap
- **THEN** the eval-service SHALL defer additional judge calls until capacity is available rather than exceeding the cap

#### Scenario: Concurrency cap is derived from durable state
- **WHEN** a worker selects pending targets to evaluate while other targets of the same game are already in flight
- **THEN** the number it takes on SHALL be limited by the recorded count of in-flight targets, so the cap holds without any in-process registry of running work

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

### Requirement: Per-evaluation judge configuration

The eval-service SHALL accept an optional per-evaluation `judge` configuration — provider, model, reasoning effort, a custom prompt/rubric, a set of rules-skill names, and a set of skill reference selections — that overrides the server defaults for that evaluation only, and SHALL record the model and provider actually used on each verdict's evaluator metadata. Selected skill names SHALL be resolved to skill content and supplied to the judge; an unknown skill name SHALL be rejected. Selected references SHALL be resolved to reference content and supplied to the judge; an unresolvable reference SHALL be rejected.

A judge configuration that selects no references SHALL produce exactly the judge prompt it produced before reference selection existed, so verdicts recorded under such a configuration remain comparable across the change.

#### Scenario: Request overrides the judge model and skills

- WHEN an evaluation request supplies a `judge` object with a `model_name`, `reasoning` effort, and a list of valid `skills`
- THEN the eval-service evaluates the selected targets with that model and reasoning, includes the named skills' content in the judge prompt, and records the used model/provider on the resulting verdict

#### Scenario: Request selects skill references

- WHEN an evaluation request supplies a `judge` object naming valid skill reference selections
- THEN the eval-service includes those references' content in the judge prompt alongside any selected skills

#### Scenario: Omitted judge config falls back to server defaults

- WHEN an evaluation request omits the `judge` object or individual fields
- THEN the eval-service uses the configured default judge model/provider/reasoning for the missing fields

#### Scenario: Unknown skill is rejected

- WHEN an evaluation request names a skill that does not exist under the configured skill roots
- THEN the eval-service rejects the request with a client error and does not start any evaluation

#### Scenario: A configuration without references is unchanged

- WHEN an evaluation request supplies a `judge` object selecting skills but no references
- THEN the judge prompt is byte-identical to the prompt that configuration produced before reference selection existed

### Requirement: Streaming evaluation progress

The eval-service SHALL expose a Server-Sent Events stream for an evaluation request that emits per-target status transitions, incremental judge output, completed verdicts, and a terminal completion event.

#### Scenario: Client streams status and verdict

- WHEN a client connects to the evaluation request's SSE stream while targets are processing
- THEN it receives an initial status snapshot, status events on each target transition, incremental judge output events, a verdict event when a target completes, and a final done event before the stream closes

### Requirement: Cancellable evaluation

The eval-service SHALL support cancelling an evaluation request, marking all non-terminal targets as `cancelled`, aborting any in-flight judge call, and writing no verdict for cancelled targets. `cancelled` SHALL be a terminal target state reflected in the request-status aggregate.

#### Scenario: Cancel an in-flight evaluation

- WHEN a cancel request is issued for an evaluation request that has pending or running targets
- THEN those targets transition to `cancelled`, any in-flight judge call is aborted, no verdict is written for them, and the stream reports the cancellation and closes

#### Scenario: Cancel a finished request is a no-op

- WHEN a cancel request is issued for an evaluation request whose targets are all terminal
- THEN the eval-service makes no changes and reports zero cancelled targets

### Requirement: Verdict identity reflects the judge configuration

A verdict's history identity SHALL incorporate the resolved judge configuration (model, provider, prompt override, skills, skill references, reasoning), so that a forced re-evaluation of the same target with a DIFFERENT judge is recorded as a distinct verdict rather than discarded by history deduplication, while an identical re-evaluation still deduplicates. The judge configuration's identity SHALL be independent of the ORDER of the selected skills and of the ORDER of the selected references, so that the same selection in a different order is treated as identical.

A judge configuration that selects no references SHALL have the same identity it had before reference selection existed, so a verdict recorded before the change still deduplicates against an identical re-evaluation after it.

#### Scenario: Forced re-eval with a different judge is recorded

- WHEN a target already has a verdict and is re-evaluated with `force` using a different judge model, prompt, skill selection, or reference selection
- THEN a new, distinct verdict event is committed to history (not dropped by dedup)

#### Scenario: Identical re-eval still dedupes

- WHEN the same target is evaluated twice with the same judge configuration
- THEN the verdict is stored exactly once

#### Scenario: Re-eval with reordered skills still dedupes

- WHEN the same target is evaluated twice with the same skill SET supplied in a different order (and all other judge settings identical)
- THEN the two evaluations produce the same idempotency key and the verdict is stored exactly once (no spurious second event)

#### Scenario: Re-eval with reordered references still dedupes

- WHEN the same target is evaluated twice with the same reference SET supplied in a different order (and all other judge settings identical)
- THEN the two evaluations produce the same idempotency key and the verdict is stored exactly once

#### Scenario: A reference-free configuration keeps its prior identity

- WHEN a target evaluated before reference selection existed is re-evaluated under the same judge configuration afterwards
- THEN the idempotency key is unchanged and the re-evaluation deduplicates

### Requirement: Cancellation prevents verdict write-back

A target that is cancelled before or during evaluation SHALL NOT have a verdict written to history.

#### Scenario: Cancel before the task registers

- WHEN a target is cancelled in the window between being claimed (`running`) and its task registering as in-flight
- THEN no verdict is written to history for that target

### Requirement: Bounded judge input
The judge input SHALL be reduced by PROJECTION before any character bound is applied: a recorded raw game state SHALL be projected to the information a judge needs to rule on a play — round, phase, per-seat vitals, and the visible cards per zone with the identifiers the move's arguments reference — rather than being character-clipped as recorded. Hidden information SHALL remain hidden: face-down cards and undrawn deck contents SHALL be reported as a count, never by name. A recorded state whose shape the projection does not recognise SHALL be sent as recorded rather than dropped. A configurable character bound SHALL remain as a backstop, and any truncation SHALL be marked in the input and logged.

A per-move judge input SHALL carry the agent moves of THAT MOVE'S OWN ROUND as context, in both directions — the moves recorded earlier in the round and the moves recorded later in it — rather than a fixed count of the nearest moves in the timeline. The round SHALL be the window: the context SHALL NOT extend into an adjacent round, and SHALL NOT stop short of the round's end, so that a move belonging to a multi-call play is always accompanied by the rest of that play while the input never grows with the length of the game. When the round containing a move cannot be determined from recorded state, the input SHALL fall back to a bounded count of the nearest agent moves either side, so a move never loses its context because boundary detection produced nothing.

The moves included as context SHALL NOT be filtered by the non-strategic taxonomy: an action that is skipped as an evaluation TARGET SHALL still appear as context, because it carries the agent's intent even when it carries no gradeable decision.

Configurable per-side bounds SHALL remain as safety backstops against a pathological round, SHALL NOT be the mechanism that decides the window, and it SHALL remain possible to configure the following-moves side away entirely so an operator can grade with no hindsight.

A round-level or game-level judge input SHALL carry the recorded game state for the end of its span, falling back to the nearest recorded state at or before the closing sequence when the closing event itself carries none, so a roll-up is never graded with no board.

#### Scenario: Large game does not overflow a small model
- **WHEN** a whole-game (or large) evaluation would exceed the configured input bound
- **THEN** the input is truncated to fit and the truncation is recorded, rather than sending an oversized prompt

#### Scenario: Recorded internal engine data never reaches the judge
- **WHEN** a per-move evaluation is assembled from a recorded raw game state that contains an internal engine change log, plugin configuration, layout data and full card definitions alongside the board
- **THEN** the judge input SHALL contain the board — the round, the phase, each seat's vitals, and the visible cards in each zone — and SHALL NOT contain the internal change log, plugin configuration or layout data, and SHALL be a small fraction of the recorded state's size

#### Scenario: Hidden information stays hidden
- **WHEN** the projected state includes a zone holding undrawn deck cards or face-down cards
- **THEN** those cards SHALL be reported only as a count under a hidden marker, and their names SHALL NOT appear anywhere in the judge input

#### Scenario: Unrecognised state shape is preserved
- **WHEN** a recorded state is not in the raw shape the projection understands
- **THEN** it SHALL be serialised as recorded and bounded by the configured character limit, so no content is silently discarded

#### Scenario: Move context spans the whole round and nothing beyond it
- **WHEN** a per-move evaluation is assembled for a move that sits in the middle of a detected round, with agent moves recorded both earlier and later in that round and further agent moves recorded in the adjacent rounds
- **THEN** the input SHALL include every agent move of that round on both sides of the graded move, and SHALL NOT include any agent move belonging to another round

#### Scenario: Following moves in the round are attached, not only preceding ones
- **WHEN** the graded move is the first agent move of its round and further agent moves follow it within the same round
- **THEN** the input SHALL include those following moves as context, and SHALL NOT be limited to the moves preceding the graded one

#### Scenario: Input does not grow with the length of the game
- **WHEN** a per-move evaluation is assembled for a move in a long recorded game with many rounds
- **THEN** the size of the attached move context SHALL be determined by the graded move's own round and SHALL NOT grow with the total number of moves in the game

#### Scenario: Undetectable round falls back to a bounded neighbour count
- **WHEN** a per-move evaluation is assembled for a move that no detected round span contains
- **THEN** the input SHALL include at most the configured number of nearest preceding and following agent moves, rather than no context at all

#### Scenario: Skipped actions still appear as context
- **WHEN** the graded move's round contains an action the non-strategic taxonomy would skip as a target, such as a card search
- **THEN** that action SHALL still appear in the attached move context

#### Scenario: Backstop bounds a pathological round without deciding the window
- **WHEN** a round contains more agent moves on one side of the graded move than the configured per-side backstop
- **THEN** the input SHALL include at most that many moves from that side, keeping the ones nearest the graded move

#### Scenario: Window size is configurable including no hindsight
- **WHEN** an operator configures the following-moves side to zero
- **THEN** the judge input SHALL contain no moves recorded after the one being graded, even within the same round

#### Scenario: Round roll-up is graded against a board
- **WHEN** a round's closing sequence is an agent move, which carries no recorded state of its own
- **THEN** the round's judge input SHALL carry the nearest recorded state at or before that sequence rather than no state

### Requirement: Non-strategic actions are skipped with a recorded reason
The eval-service SHALL NOT spend a judge call on a recorded action that commits no game state a player could get wrong. The classification SHALL turn on whether the action commits game state in a way a player could get wrong, NOT on whether the underlying tool reads or writes: searching a card database cannot be a wrong decision, whereas taking a card into hand can be, so a search SHALL be treated as non-strategic while drawing or playing a card SHALL be evaluated.

The set of non-strategic actions SHALL be operator-configurable, and its default SHALL cover read-only queries, session and room plumbing, and pre-game setup that establishes the starting position. Any action outside the configured set — including every action name the service does not recognise — SHALL be evaluated, so that a new or renamed action can never be skipped by accident.

A skipped non-strategic target SHALL be recorded as `skipped` carrying a reason that names the action and why it was skipped, and SHALL NOT be recorded as completed and SHALL NOT have a verdict written to history. The `skipped` status SHALL be reserved for this deliberate skip: a target that FAILED is recorded as `failed`, so a client can present a skip and an error differently. Skipping SHALL be possible to disable entirely by configuration.

A round-level or game-level roll-up SHALL exclude non-strategic moves from the moves it grades and SHALL state how many were excluded, so a roll-up score is not influenced by ungradeable actions. A roll-up whose span contains only non-strategic moves SHALL still be produced; the skip is a move-level judgement.

#### Scenario: Searching for a card is skipped, taking one into hand is not
- **WHEN** the eval-service evaluates a recorded move whose action is a card or set search
- **THEN** it SHALL record the target as `skipped` with a reason naming the action, SHALL NOT invoke the judge, and SHALL NOT write a verdict
- **AND WHEN** the recorded move's action instead draws a card into hand or plays a card
- **THEN** the eval-service SHALL evaluate it normally

#### Scenario: A skipped action cannot be mistaken for a passing verdict
- **WHEN** a client inspects an evaluation request that contained non-strategic targets
- **THEN** each such target SHALL appear with terminal status `skipped` and its stated reason, and SHALL NOT appear as completed or carry a score

#### Scenario: A skipped action cannot be mistaken for a failure either
- **WHEN** an evaluation request contains both a deliberately skipped non-strategic target and a target that failed
- **THEN** the skipped target SHALL carry status `skipped` and the failed target status `failed`, so a client can present the failure as a problem and the skip as routine

#### Scenario: Unrecognised action is evaluated
- **WHEN** a recorded move names an action the service's taxonomy does not know
- **THEN** the eval-service SHALL evaluate it rather than skip it

#### Scenario: Skip set is configurable in both directions
- **WHEN** an operator supplies an explicit set of non-strategic action names
- **THEN** that set SHALL replace the built-in default, so an action the default skipped is evaluated unless it is listed
- **AND WHEN** an operator disables non-strategic skipping
- **THEN** every recorded move SHALL be evaluated

#### Scenario: Roll-up states what it left out
- **WHEN** a round roll-up's span contains non-strategic moves
- **THEN** those moves SHALL be omitted from the moves the judge is asked to grade and the input SHALL state how many were omitted

### Requirement: Hardened evaluation endpoints

The eval-service SHALL restrict CORS to a configurable allowlist (not `*`), validate `game_id` against a strict pattern at the route boundary, and url-encode `game_id` in outbound service-to-service URLs.

#### Scenario: Malformed game id rejected

- WHEN a request carries a `game_id` that does not match the allowed pattern
- THEN it is rejected at the boundary before any database or outbound-HTTP use

### Requirement: Cross-game evaluation request listing
The eval-service SHALL expose an endpoint to list evaluation requests across all games,
ordered newest-first, so a client can present a persistent queue of in-progress and recent
evaluations without knowing each `request_id` in advance. Each listed request SHALL be
summarized with its `request_id`, `game_id`, overall status (derived from its targets),
`created_at`, and a per-target summary carrying at least each target's `scope`, `target_seq`,
`round_span`, `status`, and the recorded error detail of any target that has one — including a
target that is still in progress — so a client polling the listing can report a failure while
the request is running. The endpoint SHALL support filtering to active requests (those
with at least one non-terminal target) and SHALL bound the number of returned requests with a
capped `limit`. The listing SHALL be derived from durable storage, not from any in-memory queue.

#### Scenario: List recent requests across games
- **WHEN** a client requests the evaluation list
- **THEN** the eval-service SHALL return the recent evaluation requests across all games ordered
  newest-first, each with its overall status and per-target scope/seq/round_span/status summary

#### Scenario: Listing carries the error detail of an in-progress failure
- **WHEN** a client requests the evaluation list while a request has a still-running target whose
  last judge attempt failed
- **THEN** that target's summary SHALL carry the recorded error detail, so the client can report
  the failure without waiting for the request to reach a terminal status

#### Scenario: Filter to active requests
- **WHEN** a client requests the evaluation list with the active filter enabled
- **THEN** the eval-service SHALL return only requests that have at least one non-terminal target,
  omitting requests whose targets are all completed/skipped/failed/cancelled

#### Scenario: Bounded result size
- **WHEN** a client requests the evaluation list with a `limit` larger than the allowed maximum
- **THEN** the eval-service SHALL return no more than the capped maximum number of requests

### Requirement: Clearing terminal evaluation requests
The eval-service SHALL expose endpoints to clear evaluation requests from its queue tracking,
both individually and in bulk. A request MAY be cleared ONLY when it is fully terminal (no target
is still pending or running); a request with a non-terminal target SHALL NOT be cleared (it can
only be cancelled). Clearing SHALL remove only the eval-service's own request and target tracking
rows; verdicts already recorded as history-service events are independent and SHALL NOT be
affected. These endpoints are cross-game (not nested under `/games/{game_id}`).

#### Scenario: Delete a terminal request
- **WHEN** a client requests deletion of an evaluation request whose targets are all terminal
- **THEN** the eval-service SHALL remove that request and its target rows and SHALL no longer
  return it from the cross-game listing or the per-request lookup

#### Scenario: Reject deleting a non-terminal request
- **WHEN** a client requests deletion of an evaluation request that still has at least one
  pending or running target
- **THEN** the eval-service SHALL reject the request with a conflict (HTTP 409) and SHALL leave
  the request and its targets unchanged

#### Scenario: Delete a request that does not exist
- **WHEN** a client requests deletion of an unknown `request_id`
- **THEN** the eval-service SHALL respond with not found (HTTP 404)

#### Scenario: Clear all terminal requests
- **WHEN** a client requests a bulk clear of the evaluation queue
- **THEN** the eval-service SHALL remove every request that has no non-terminal target, SHALL
  leave requests with a pending or running target intact, and SHALL return the count of requests
  deleted

### Requirement: Hierarchical evaluation levels with dependency
The eval-service SHALL support three evaluation levels with a dependency relationship —
move → round → game — where a round-level evaluation depends on the evaluations of its
constituent moves and a game-level evaluation depends on the evaluations of its constituent
rounds. A higher-level evaluation SHALL NOT be produced unless every component beneath it has
been evaluated.

#### Scenario: Round depends on its moves
- **WHEN** a round-level evaluation is produced
- **THEN** every agent move within that round SHALL have an evaluation that the round evaluation
  is grounded in

#### Scenario: Game depends on its rounds
- **WHEN** a game-level evaluation is produced
- **THEN** every round within that game SHALL have an evaluation that the game evaluation is
  grounded in

### Requirement: Auto-grading cascade
The eval-service SHALL, when a round-level or game-level evaluation is requested and some
required lower-level components are not yet evaluated, first evaluate the missing components
(moves, then rounds) and then evaluate the requested level, so a single request fans out across
the entire subtree it requires. Already-evaluated components SHALL be reused unless a forced
re-evaluation is requested (config-aware idempotency).

#### Scenario: Game request cascades to moves and rounds
- **WHEN** a game-level evaluation is requested for a game whose moves and rounds are not all
  evaluated
- **THEN** the eval-service SHALL evaluate the ungraded moves, then the rounds, then the game,
  reusing any components already evaluated with the same judge configuration

### Requirement: Judge-with-child-context roll-up
A round-level or game-level score SHALL be produced by the judge grading the span holistically
with the child evaluations (their scores and rationales) provided as context, rather than as a
purely numeric aggregate of child scores.

#### Scenario: Round score considers its move verdicts
- **WHEN** the eval-service produces a round-level evaluation
- **THEN** the judge SHALL be given the round's move evaluations as context and SHALL produce a
  holistic round score and rationale (not a mechanical average)

### Requirement: Per-player attribution and results
The eval-service SHALL attribute each agent move to the active player, and SHALL produce a
separate round-level and game-level result for each player who acted within the span — scoring
that player's moves (round) and that player's rounds (game). Move-level evaluations are
attributed to their acting player. Each evaluation result SHALL carry the `player` it pertains
to. A single-player game has one player.

Attribution SHALL prefer an acting-player id explicitly recorded on the move over any inferred
value. When a move carries an explicitly recorded player, that value SHALL be used even if the
player count cannot be derived from recorded game state. Only when no explicit value is present
SHALL the eval-service fall back to deriving the active player from the game state at that move.

#### Scenario: Separate per-player results for a multi-player span
- **WHEN** a round or game spanning the actions of more than one player is evaluated
- **THEN** the eval-service SHALL produce a distinct evaluation result for each player who acted,
  each scoring only that player's contributions, each carrying that player's id

#### Scenario: Move attributed to its acting player
- **WHEN** a move is evaluated
- **THEN** the evaluation SHALL carry the id of the player who was active for that move

#### Scenario: Explicitly recorded player wins over inference
- **WHEN** a move was recorded with an explicit acting-player id and the game state would imply a
  different player
- **THEN** the eval-service SHALL attribute the move to the explicitly recorded player

#### Scenario: Explicit player without derivable state
- **WHEN** a move was recorded with an explicit acting-player id and the recorded state does not
  reveal how many players are in the game
- **THEN** the eval-service SHALL attribute the move to the explicitly recorded player rather than
  defaulting to the single-player id

#### Scenario: Legacy games keep heuristic attribution
- **WHEN** a game recorded without explicit acting-player ids is evaluated
- **THEN** the eval-service SHALL attribute its moves from the game state exactly as before

### Requirement: Evaluation errors are reported live with redacted detail
The eval-service SHALL report an evaluation failure as it happens, not only when the target reaches a terminal state. Every failed judge attempt SHALL be recorded with its reason on the target while that target is still in progress, and SHALL be pushed to the live channel so a connected client learns of it immediately. A failure SHALL NOT be reported only through logs.

The recorded reason SHALL be held in durable storage (the service's PostgreSQL), never in process memory, so any replica, poller or stream reads the same detail. Reporting SHALL use the service's existing live channel and target-status projections; it SHALL NOT introduce a second transport.

A retry that eventually succeeds SHALL clear the recorded in-progress error, so a transient failure that was overcome is not left behind as a false failure on a completed target.

All error detail the eval-service records or serves SHALL be redacted and length-bounded before it is stored. Credentials SHALL NOT appear in it: authorization headers and bearer tokens, named gateway key headers, `api_key`/`access_token`/`client_secret`/`password`-style fields, and bare provider key literals SHALL be replaced with a redaction marker. The detail SHALL be truncated to a bounded length so a provider response echoing a full request body — the judge prompt and a recorded game state — can never be persisted or streamed. Redaction SHALL be applied at the storage boundary so no recording path can bypass it, and SHALL run before truncation so a secret beyond the cut cannot survive.

#### Scenario: A failed judge attempt is visible during the run
- **WHEN** a judge attempt for a target fails and the eval-service is about to retry it
- **THEN** the attempt's reason SHALL be recorded on that target in durable storage while the target's status is still in progress, the live channel SHALL be signalled, and a client reading the target's status (by stream or by polling) SHALL see the reason before the request reaches a terminal state

#### Scenario: A recovered retry leaves no false failure
- **WHEN** an earlier judge attempt failed and a later attempt for the same target succeeds
- **THEN** the target SHALL be recorded as completed with its verdict and SHALL NOT retain the earlier attempt's error detail

#### Scenario: Terminal failure detail reaches the client
- **WHEN** a target reaches a terminal `failed` state
- **THEN** its reason SHALL be included in the per-target results of the request-status endpoint, the cross-game listing, and the live stream's status snapshot

#### Scenario: Credentials are never present in error detail
- **WHEN** a gateway or transport failure message embeds an authorization header, a bearer token, a named key header, an api-key field, or a bare provider key literal
- **THEN** the eval-service SHALL replace each with a redaction marker before storing the detail, so no credential is written to storage or served to a client

#### Scenario: A provider echoing the request body is truncated
- **WHEN** an error message carries a provider response body far larger than the recorded-detail bound — for example one echoing the judge prompt and a recorded game state
- **THEN** the eval-service SHALL store and serve only a bounded excerpt, marked as truncated

#### Scenario: A secret beyond the truncation point is still redacted
- **WHEN** an error message carries a credential positioned past the length bound
- **THEN** that credential SHALL be redacted rather than merely cut off, so shortening the message cannot reveal it

### Requirement: Round-aware grading instruction
The judge SHALL be instructed that a single game decision is normally executed as several recorded actions and SHALL be told to grade the move as the step it is within the play its round reveals. Specifically the instruction SHALL state that a legal, necessary step of a sound play SHALL NOT be scored down for accomplishing nothing on its own, and that one play SHALL NOT be charged against every action that makes it up.

The per-move judge input SHALL name the round the graded move belongs to, and SHALL label its earlier-in-round and later-in-round context distinctly, with the later-in-round context marked as completion context rather than an outcome to grade on hindsight.

Round labels presented to a judge or to a user SHALL use the round of play, which is the recorded DragnCards round number plus one, because that number counts COMPLETED rounds and therefore reads zero throughout the first round of play.

#### Scenario: Multi-call play is not scored down per call
- **WHEN** the judge is asked to grade an action that only pays a cost, such as exhausting a character, and the round context shows the action whose effect that cost paid for
- **THEN** the judge instruction SHALL direct that the action be graded as that step of that play rather than as an action that achieved nothing

#### Scenario: Later-in-round context is not an outcome to grade
- **WHEN** the per-move input includes moves recorded later in the round
- **THEN** those moves SHALL be labelled as completion context and the instruction SHALL direct the judge not to score the decision on hindsight it did not have

#### Scenario: Round labels count the round of play
- **WHEN** a recorded state reports a DragnCards round number of 0
- **THEN** every label derived from it SHALL read as round 1

### Requirement: Detected round listing
The eval-service SHALL expose a read API listing the rounds it detects for a game, so a client can select a round WITHOUT naming any sequence inside it. Each listed round SHALL carry the round number the evaluation request's round selection accepts, a presentation label, its `from_seq` and `to_seq` span, the number of agent moves in it, and the players who acted in it.

The listed number SHALL be the round of play — the SAME number the round selection accepts and the same number the History transcript shows — so a client never converts between two round-numbering schemes and cannot select the wrong round by picking the raw recorded counter.

A round the listing reports SHALL be a round the eval-service can grade, so that selecting a listed round always expands to at least one target.

#### Scenario: List a game's rounds
- **WHEN** a client requests the round listing for a `game_id` with recorded events
- **THEN** the eval-service SHALL return each detected round with its round-of-play number, label, sequence span, agent-move count, and acting players

#### Scenario: The listed number is the number the selection accepts
- **WHEN** a recorded state reports a DragnCards round number of 0 for the first round of play
- **THEN** that round SHALL be listed as round 1, and submitting round 1 SHALL select that same round

#### Scenario: A listed round is selectable by number alone
- **WHEN** a client submits a round-scope evaluation naming only the round numbers from that listing
- **THEN** the eval-service SHALL expand the request to that round's targets without requiring any move sequence

#### Scenario: Round listing for an unknown game
- **WHEN** a client requests the round listing for a `game_id` with no recorded events
- **THEN** the eval-service SHALL respond 404 rather than an empty success

### Requirement: Parallel evaluation without in-memory state
The eval-service SHALL evaluate multiple targets concurrently, and the concurrency SHALL be bounded WITHOUT any in-process queue, set, or dictionary of work: the pending set, the claim, and the in-flight count SHALL all live in the service's database. Concurrent evaluation SHALL neither lose nor duplicate a result — every claimed target SHALL reach a terminal status exactly once and SHALL produce at most one verdict.

A higher-level target that is re-deferred because its children are still in flight SHALL NOT cause the worker to spin: a drain cycle in which no target made progress SHALL be treated as an idle cycle.

#### Scenario: Multiple targets of one request evaluate in parallel
- **WHEN** an evaluation request expands to more targets than the per-game concurrency cap
- **THEN** up to that cap SHALL be evaluated concurrently and the rest SHALL wait for capacity, rather than being evaluated one at a time

#### Scenario: Parallel evaluation neither loses nor duplicates a verdict
- **WHEN** many targets of a game are drained concurrently
- **THEN** each target SHALL end in exactly one terminal status and each SHALL have at most one verdict written to history, with none left pending

#### Scenario: No in-process registry bounds the work
- **WHEN** the service restarts with targets still recorded as in flight
- **THEN** the concurrency bound SHALL still hold, because it is computed from the recorded target statuses rather than from a process-local structure

#### Scenario: An all-deferred cycle does not hot-loop
- **WHEN** every target a drain cycle claimed is re-deferred because its children are still being graded
- **THEN** the worker SHALL treat the cycle as idle and wait before draining again

### Requirement: Verdict comparability across evaluator versions
Every verdict SHALL record the evaluator version that produced it, and a change that alters what the judge is shown or asked SHALL increment that version. Verdicts produced under different evaluator versions SHALL NOT be aggregated together into one figure; an aggregate SHALL be computed from a single evaluator version and SHALL disclose how many verdicts it excluded.

#### Scenario: Changing the judge input increments the evaluator version
- **WHEN** the assembled judge input or the grading instruction changes in a way that shifts scores
- **THEN** the recorded evaluator version SHALL change, so a verdict states which regime produced it

#### Scenario: Aggregates are not mixed across versions
- **WHEN** a game holds verdicts from more than one evaluator version
- **THEN** an aggregate score SHALL be computed from one version only and SHALL disclose the number of verdicts left out

#### Scenario: Re-evaluation under a new version is a distinct record
- **WHEN** a target that already has a verdict from an earlier evaluator version is force re-evaluated
- **THEN** the new verdict SHALL be recorded as its own history event rather than deduplicated against the earlier one

### Requirement: A judge can be given a skill's reference files, not only its SKILL.md

A rules skill's reference files are part of its content. The eval-service SHALL accept, as part of a per-evaluation `judge` configuration, a set of reference selections naming a skill and a reference file within it, SHALL resolve each selection to that file's content under the configured skill roots, and SHALL supply that content to the judge alongside the selected skills.

A reference SHALL be selectable without its skill's `SKILL.md`, and when it is, the judge SHALL be told that it holds references from that skill rather than the whole skill.

A selection naming a skill that does not exist, or a reference that cannot be resolved within that skill, SHALL be rejected before any evaluation target is enqueued.

#### Scenario: A selected reference reaches the judge

- **WHEN** an evaluation request supplies a `judge` configuration selecting a skill and one of that skill's reference files
- **THEN** the judge SHALL be given that reference file's content, attributed to the skill it belongs to

#### Scenario: A reference is selected without its skill

- **WHEN** an evaluation request selects a reference file but not the skill's `SKILL.md`
- **THEN** the judge SHALL be given that reference's content in a block that states it holds references from that skill only

#### Scenario: An unresolvable reference is rejected

- **WHEN** an evaluation request names a reference that does not exist within its skill
- **THEN** the request SHALL be rejected as a client error and no evaluation target SHALL be enqueued

### Requirement: A reference selection cannot read outside its skill directory

A reference selection is caller-supplied and SHALL be confined to the directory of the skill it names. The eval-service SHALL refuse a selection that resolves outside that directory by any means, including an absolute path, a parent-directory traversal, or a symbolic link. It SHALL additionally refuse a selection that is not a markdown file, that names a directory, that names the skill's own `SKILL.md`, or whose supplied form is not the canonical relative path of the file it resolves to.

A refusal SHALL NOT disclose whether the out-of-bounds target exists.

#### Scenario: An absolute path is refused

- **WHEN** a reference selection supplies an absolute filesystem path
- **THEN** the eval-service SHALL refuse the selection and read no file

#### Scenario: A parent-directory traversal is refused

- **WHEN** a reference selection uses `..` to name a path outside its skill directory
- **THEN** the eval-service SHALL refuse the selection and read no file

#### Scenario: A symbolic link out of the skill is refused

- **WHEN** a reference selection names a markdown file inside the skill directory that is a symbolic link to a file outside it
- **THEN** the eval-service SHALL refuse the selection and read no file

#### Scenario: A non-canonical path form is refused

- **WHEN** a reference selection names a path that resolves inside the skill directory but is not that file's canonical relative path
- **THEN** the eval-service SHALL refuse the selection

### Requirement: Reference selections are bounded and refuse rather than truncate

The eval-service SHALL bound how much reference content one evaluation may carry by a total SIZE budget across the selection, and SHALL NOT bound it by a count of selected references. A count ceiling MAY exist on the request schema solely to reject an absurd request body before any file is read, and SHALL be set high enough that no selection over the available reference corpus can reach it.

The size budget SHALL be DERIVED from the judge model's configured context window rather than fixed: the window, expressed in characters, less what the rest of the judge prompt may occupy at its already-configured caps — the completion reserve, the projected game states, the round/neighbour context, the roll-up context, the prompt frame, any prompt override, and the `SKILL.md` content the same request selects. Because one judge configuration serves the move, round and game prompts and they carry different elements, the reserve SHALL be the LARGEST of those three prompts rather than their sum. An operator MAY configure an additional character cap, which SHALL only ever LOWER the derived budget and SHALL NOT raise it above what the window admits.

A selection exceeding the budget SHALL be rejected as a client error before any evaluation target is enqueued. The error SHALL state the measured total, the budget, the amount by which the budget was exceeded, each reserve term that produced the budget, which prompt was the worst case, and the settings that would change it, so the operator can act on the refusal rather than only learn of it. These SHALL be stated whether the window or an operator's own cap produced the budget, because the reserve terms are what name the settings to change.

Reference content SHALL NOT be truncated to fit a bound: a partially delivered rules reference is indistinguishable to the judge from a complete one, and grading against a silently clipped rulebook is the failure this requirement exists to prevent.

#### Scenario: A selection is refused only when it cannot fit the window

- **WHEN** an evaluation request selects references whose combined size exceeds the budget derived from the configured context window
- **THEN** the request SHALL be rejected as a client error and no evaluation target SHALL be enqueued

#### Scenario: A selection that fits the window is accepted whatever its count

- **WHEN** an evaluation request selects every reference file of a skill, and their combined size is within the derived budget
- **THEN** the selection SHALL be accepted regardless of how many reference files it names

#### Scenario: The refusal states the arithmetic that produced it

- **WHEN** a selection is refused for exceeding the budget
- **THEN** the error SHALL state the measured total, the budget, the overage, the reserve terms subtracted from the context window, and the settings that would raise the budget

#### Scenario: A larger context window admits a larger selection

- **WHEN** the configured judge context window is raised and the same selection is submitted again
- **THEN** a selection previously refused for exceeding the budget SHALL be accepted once the window admits it

#### Scenario: An operator cap lowers but never raises the budget

- **WHEN** an operator configures a total reference character cap
- **THEN** the effective budget SHALL be the lower of that cap and the window-derived budget

#### Scenario: Reference content is never clipped

- **WHEN** a reference selection is accepted
- **THEN** each selected reference's content SHALL be supplied to the judge in full

### Requirement: Every repeated element of a judge prompt is bounded

A reference budget derived from the context window is only sound if the rest of the prompt honours the caps it reserves against. Every element of a judge prompt that repeats per move, per round or per already-graded child SHALL therefore be bounded in both count and size.

A round roll-up's move list SHALL clip each move's recorded reasoning by the same configured cap a move prompt's neighbour list uses, since it is the same field rendered for the same purpose. A roll-up prompt's already-graded child verdicts SHALL be bounded by count and each rationale by a configured character cap, and any omission SHALL be stated in the prompt and logged.

A move's recorded arguments SHALL remain unclipped, because legality is judged on them and clipping them would change verdicts rather than merely shorten a prompt.

#### Scenario: A verbose move cannot dominate a round prompt

- **WHEN** a round roll-up renders a move whose recorded reasoning exceeds the configured per-move reasoning cap
- **THEN** that reasoning SHALL be clipped and marked as clipped

#### Scenario: Roll-up context is bounded in count and in size

- **WHEN** a roll-up prompt has more already-graded child verdicts than the configured ceiling, or a child rationale longer than the configured cap
- **THEN** the excess children SHALL be omitted with the omission stated in the prompt, and each rendered rationale SHALL be clipped to the cap

