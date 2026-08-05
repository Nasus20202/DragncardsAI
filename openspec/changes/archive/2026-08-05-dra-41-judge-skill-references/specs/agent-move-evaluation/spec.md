## ADDED Requirements

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

The eval-service SHALL bound how much reference content one evaluation may carry, both by count of selected references and by a configurable total size across the selection. A selection exceeding either bound SHALL be rejected as a client error naming the measured size and the limit.

Reference content SHALL NOT be truncated to fit a bound: a partially delivered rules reference is indistinguishable to the judge from a complete one, and grading against a silently clipped rulebook is the failure this requirement exists to prevent.

#### Scenario: An over-budget selection is refused

- **WHEN** an evaluation request selects references whose combined size exceeds the configured total reference budget
- **THEN** the request SHALL be rejected as a client error stating the measured total and the configured limit, and no evaluation target SHALL be enqueued

#### Scenario: Reference content is never clipped

- **WHEN** a reference selection is accepted
- **THEN** each selected reference's content SHALL be supplied to the judge in full

## MODIFIED Requirements

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
