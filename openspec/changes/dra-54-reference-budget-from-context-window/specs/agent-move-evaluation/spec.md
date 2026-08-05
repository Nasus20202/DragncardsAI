## ADDED Requirements

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

## MODIFIED Requirements

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
