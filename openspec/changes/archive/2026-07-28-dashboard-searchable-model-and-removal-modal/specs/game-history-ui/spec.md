## MODIFIED Requirements

### Requirement: Play-parity judge configuration in the evaluate control

The dashboard Evaluate control SHALL let the user configure the judge per evaluation — provider and model, reasoning effort, a custom prompt/rubric, and selected rules skills — reusing the same provider and skill sources as the Play flow, and SHALL include the chosen configuration in the evaluation request, omitting empty fields.

Judge model selection SHALL be searchable, using the same shared searchable model picker as the Play settings panel: typing SHALL narrow the offered models from the selected provider's catalog by case-insensitive substring match, and opening the control SHALL offer that provider's whole catalog. Narrowing the list alone SHALL NOT change the drafted model — only choosing an offered model SHALL. A drafted model the selected provider does not offer SHALL remain selectable, and the control SHALL be disabled when no models are available. Provider selection, the reasoning controls, the prompt/rubric field, and the skills selection are unaffected.

#### Scenario: Configuring and submitting a judge

- WHEN the user selects a provider/model, sets reasoning, optionally edits the prompt, picks skills, and submits an evaluation
- THEN the request carries the chosen judge configuration and the resulting verdict reflects the selected model

#### Scenario: Searching for a judge model

- WHEN the user types part of a model name into the judge model control
- THEN only the selected provider's models whose names contain that text are offered, and the drafted judge model is unchanged until one of them is chosen

#### Scenario: Drafted model outside the provider catalog

- WHEN the drafted judge model is not among the selected provider's offered models
- THEN the judge model control SHALL still show and offer that model rather than silently dropping it
