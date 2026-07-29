## MODIFIED Requirements

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

## ADDED Requirements

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
