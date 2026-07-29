# agent-move-evaluation

## MODIFIED Requirements

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
