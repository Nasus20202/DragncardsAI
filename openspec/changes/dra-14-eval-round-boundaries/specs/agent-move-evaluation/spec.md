## MODIFIED Requirements

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

### Requirement: Structured verdict written back as an evaluator event
The eval-service SHALL write each evaluation verdict back to the history-service through its HTTP ingest endpoint as a versioned event envelope with actor `evaluator`, whose payload contains an overall 0-10 score, four per-criterion 0-10 scores (`rules_legality`, `strategic_quality`, `tempo_efficiency`, `threat_resource`), a rationale, the evaluation scope, the `evaluator_version`, and the target move `seq` or round span it grades, using an idempotency key derived from `(game_id, target_seq, scope, evaluator_version)`.

A change to HOW the eval-service derives what a verdict grades — including how round spans are detected and numbered — SHALL be surfaced by a change to `evaluator_version`, so verdicts produced under different derivations are distinguishable in recorded history rather than presented as comparable. Verdicts already recorded SHALL NOT be rewritten, re-scored, or deleted by such a change; re-grading SHALL remain an explicit user-requested re-evaluation.

#### Scenario: Verdict ingested as an evaluator event
- **WHEN** the eval-service completes a verdict for a `game_id` and `target_seq`
- **THEN** the eval-service SHALL submit it to the history-service HTTP ingest endpoint as an envelope with actor `evaluator` whose payload includes the per-criterion scores, the overall score, the rationale, the scope, and the target reference

#### Scenario: Verdict references the graded move or round
- **WHEN** the eval-service writes a verdict
- **THEN** the payload SHALL identify the graded target by `target_seq` for a move and additionally by the round span for a round, so it is `seq`-correlated to the move/round on the same game timeline

#### Scenario: Duplicate verdict write-back stored once
- **WHEN** the same verdict for a `(game_id, target_seq, scope, evaluator_version)` is written back more than once
- **THEN** the history-service SHALL store it exactly once because the verdict carries a stable idempotency key

#### Scenario: A change in span derivation is not applied silently
- **WHEN** the eval-service changes how a round's span is derived, so a new round verdict grades a different span from an older verdict of the same round
- **THEN** the new verdicts SHALL carry a different `evaluator_version` from the older ones, and the older verdicts SHALL remain in history exactly as recorded
