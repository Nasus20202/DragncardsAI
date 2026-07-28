# agent-move-evaluation Specification

## Purpose
TBD - created by archiving change agent-move-evaluation. Update Purpose after archive.
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

### Requirement: Per-evaluation judge configuration

The eval-service SHALL accept an optional per-evaluation `judge` configuration — provider, model, reasoning effort, a custom prompt/rubric, and a set of rules-skill names — that overrides the server defaults for that evaluation only, and SHALL record the model and provider actually used on each verdict's evaluator metadata. Selected skill names SHALL be resolved to skill content and supplied to the judge; an unknown skill name SHALL be rejected.

#### Scenario: Request overrides the judge model and skills

- WHEN an evaluation request supplies a `judge` object with a `model_name`, `reasoning` effort, and a list of valid `skills`
- THEN the eval-service evaluates the selected targets with that model and reasoning, includes the named skills' content in the judge prompt, and records the used model/provider on the resulting verdict

#### Scenario: Omitted judge config falls back to server defaults

- WHEN an evaluation request omits the `judge` object or individual fields
- THEN the eval-service uses the configured default judge model/provider/reasoning for the missing fields

#### Scenario: Unknown skill is rejected

- WHEN an evaluation request names a skill that does not exist under the configured skill roots
- THEN the eval-service rejects the request with a client error and does not start any evaluation

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

A verdict's history identity SHALL incorporate the resolved judge configuration (model, provider, prompt override, skills, reasoning), so that a forced re-evaluation of the same target with a DIFFERENT judge is recorded as a distinct verdict rather than discarded by history deduplication, while an identical re-evaluation still deduplicates. The judge configuration's identity SHALL be independent of the ORDER of the selected skills, so that the same skill set in a different order is treated as identical.

#### Scenario: Forced re-eval with a different judge is recorded

- WHEN a target already has a verdict and is re-evaluated with `force` using a different judge model or prompt
- THEN a new, distinct verdict event is committed to history (not dropped by dedup)

#### Scenario: Identical re-eval still dedupes

- WHEN the same target is evaluated twice with the same judge configuration
- THEN the verdict is stored exactly once

#### Scenario: Re-eval with reordered skills still dedupes

- WHEN the same target is evaluated twice with the same skill SET supplied in a different order (and all other judge settings identical)
- THEN the two evaluations produce the same idempotency key and the verdict is stored exactly once (no spurious second event)

### Requirement: Cancellation prevents verdict write-back

A target that is cancelled before or during evaluation SHALL NOT have a verdict written to history.

#### Scenario: Cancel before the task registers

- WHEN a target is cancelled in the window between being claimed (`running`) and its task registering as in-flight
- THEN no verdict is written to history for that target

### Requirement: Bounded judge input
The judge input SHALL be reduced by PROJECTION before any character bound is applied: a recorded raw game state SHALL be projected to the information a judge needs to rule on a play — round, phase, per-seat vitals, and the visible cards per zone with the identifiers the move's arguments reference — rather than being character-clipped as recorded. Hidden information SHALL remain hidden: face-down cards and undrawn deck contents SHALL be reported as a count, never by name. A recorded state whose shape the projection does not recognise SHALL be sent as recorded rather than dropped. A configurable character bound SHALL remain as a backstop, and any truncation SHALL be marked in the input and logged.

A per-move judge input SHALL include a CONFIGURABLE WINDOW of the agent's neighbouring moves rather than the whole recorded history, bounded independently for preceding and following moves, so that a move belonging to a multi-step play is not judged in isolation while the input does not grow with the length of the game. The following-moves portion SHALL be labelled as completion context rather than an outcome to grade, and it SHALL be possible to configure it away entirely.

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

#### Scenario: Neighbouring moves are windowed, not replayed
- **WHEN** a per-move evaluation is assembled for a move that sits in the middle of a long recorded game
- **THEN** the input SHALL include at most the configured number of preceding and following agent moves, and SHALL NOT grow with the total number of moves in the game

#### Scenario: Window size is configurable including no hindsight
- **WHEN** an operator configures the following-moves window to zero
- **THEN** the judge input SHALL contain no moves recorded after the one being graded

#### Scenario: Round roll-up is graded against a board
- **WHEN** a round's closing sequence is an agent move, which carries no recorded state of its own
- **THEN** the round's judge input SHALL carry the nearest recorded state at or before that sequence rather than no state

### Requirement: Non-strategic actions are skipped with a recorded reason
The eval-service SHALL NOT spend a judge call on a recorded action that commits no game state a player could get wrong. The classification SHALL turn on whether the action commits game state in a way a player could get wrong, NOT on whether the underlying tool reads or writes: searching a card database cannot be a wrong decision, whereas taking a card into hand can be, so a search SHALL be treated as non-strategic while drawing or playing a card SHALL be evaluated.

The set of non-strategic actions SHALL be operator-configurable, and its default SHALL cover read-only queries, session and room plumbing, and pre-game setup that establishes the starting position. Any action outside the configured set — including every action name the service does not recognise — SHALL be evaluated, so that a new or renamed action can never be skipped by accident.

A skipped non-strategic target SHALL be recorded as `skipped` carrying a reason that names the action and why it was skipped, through the same per-target skip channel a judge failure uses, and SHALL NOT be recorded as completed and SHALL NOT have a verdict written to history. Skipping SHALL be possible to disable entirely by configuration.

A round-level or game-level roll-up SHALL exclude non-strategic moves from the moves it grades and SHALL state how many were excluded, so a roll-up score is not influenced by ungradeable actions. A roll-up whose span contains only non-strategic moves SHALL still be produced; the skip is a move-level judgement.

#### Scenario: Searching for a card is skipped, taking one into hand is not
- **WHEN** the eval-service evaluates a recorded move whose action is a card or set search
- **THEN** it SHALL record the target as `skipped` with a reason naming the action, SHALL NOT invoke the judge, and SHALL NOT write a verdict
- **AND WHEN** the recorded move's action instead draws a card into hand or plays a card
- **THEN** the eval-service SHALL evaluate it normally

#### Scenario: A skipped action cannot be mistaken for a passing verdict
- **WHEN** a client inspects an evaluation request that contained non-strategic targets
- **THEN** each such target SHALL appear with terminal status `skipped` and its stated reason, and SHALL NOT appear as completed or carry a score

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
`round_span`, and `status`. The endpoint SHALL support filtering to active requests (those
with at least one non-terminal target) and SHALL bound the number of returned requests with a
capped `limit`. The listing SHALL be derived from durable storage, not from any in-memory queue.

#### Scenario: List recent requests across games
- **WHEN** a client requests the evaluation list
- **THEN** the eval-service SHALL return the recent evaluation requests across all games ordered
  newest-first, each with its overall status and per-target scope/seq/round_span/status summary

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

