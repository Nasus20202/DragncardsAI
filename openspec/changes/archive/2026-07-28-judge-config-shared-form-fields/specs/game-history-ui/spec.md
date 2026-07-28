## MODIFIED Requirements

### Requirement: Play-parity judge configuration in the evaluate control

The dashboard Evaluate control SHALL let the user configure the judge per evaluation — provider and model, reasoning effort, a custom prompt/rubric, and selected rules skills — reusing the same provider and skill sources as the Play flow, and SHALL include the chosen configuration in the evaluation request, omitting empty fields.

Judge model selection SHALL be searchable, using the same shared searchable model picker as the Play settings panel: typing SHALL narrow the offered models from the selected provider's catalog by case-insensitive substring match, and opening the control SHALL offer that provider's whole catalog. Narrowing the list alone SHALL NOT change the drafted model — only choosing an offered model SHALL. A drafted model the selected provider does not offer SHALL remain selectable, and the control SHALL be disabled when no models are available.

Every judge control SHALL be rendered from the same shared field components as the Play settings panel, so the two panels present the same configuration identically. Specifically: the provider SHALL be a labelled select and the model a labelled searchable select; enabling reasoning and selecting a skill SHALL each be a toggle switch row, not a checkbox; reasoning effort SHALL be a labelled select; reasoning max tokens SHALL be a labelled text field; and the prompt/rubric SHALL be a labelled textarea. Skills SHALL be presented as the same bordered toggle list the Play panel renders, and a skill that carries a description or metadata SHALL expose them through the row's info trigger rather than only as a native tooltip on the label. The judge panel SHALL NOT define its own input styling for these controls.

Adopting the shared components SHALL NOT change the judge panel's behavior or its automation surface: changing the provider SHALL still clamp the model to that provider's offerings, an empty provider list SHALL still offer the drafted provider id, the panel SHALL still disable every control while an evaluation is being submitted, and each control SHALL keep the test id and accessible name it already exposed.

#### Scenario: Configuring and submitting a judge

- WHEN the user selects a provider/model, sets reasoning, optionally edits the prompt, picks skills, and submits an evaluation
- THEN the request carries the chosen judge configuration and the resulting verdict reflects the selected model

#### Scenario: Searching for a judge model

- WHEN the user types part of a model name into the judge model control
- THEN only the selected provider's models whose names contain that text are offered, and the drafted judge model is unchanged until one of them is chosen

#### Scenario: Drafted model outside the provider catalog

- WHEN the drafted judge model is not among the selected provider's offered models
- THEN the judge model control SHALL still show and offer that model rather than silently dropping it

#### Scenario: Judge controls match the Play settings controls

- WHEN the user opens the Judge section of the Evaluate panel
- THEN each control SHALL be the same shared field component the Play settings panel uses for that setting, with reasoning and each skill rendered as a toggle switch row rather than a checkbox

#### Scenario: Skill descriptions are reachable in the judge panel

- WHEN a skill offered in the judge panel carries a description or metadata
- THEN its row SHALL expose an info trigger revealing that description and metadata

#### Scenario: Provider change still clamps the judge model

- WHEN the user selects a different judge provider whose catalog does not include the drafted model
- THEN the drafted judge model SHALL be replaced with the first model the newly-selected provider offers
