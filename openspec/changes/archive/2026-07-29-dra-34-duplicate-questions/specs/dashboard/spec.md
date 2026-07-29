## ADDED Requirements

### Requirement: A question's choices read as a list of targets

The dashboard SHALL lay out the choices offered by a question as a vertical list of
full-width rows, one row per choice, rather than as inline controls flowed across a
line. A question's choices carry descriptions and sentence-length labels, so flowing
them inline breaks a handful of choices across ragged lines and gives no row a
predictable width.

Each row SHALL be visually distinguishable as something to click — bounded by its own
border and responding to hover and to being pressed — so that a choice is not mistaken
for static text. A row that cannot be chosen, because the question is already resolved,
the run has ended, an answer is in flight, or the surface is read-only, SHALL be
visually distinct from one that can and SHALL NOT respond to the pointer.

A choice's label SHALL be shown above its description rather than run together with
it. Both SHALL wrap within the row, and neither SHALL extend beyond the width of the
card containing it. Where a length bound is applied, it SHALL be generous enough that
an ordinary description is shown in full, and it SHALL bound the text vertically
rather than horizontally, so that no part of a description is lost off the edge of the
transcript.

The choice rows SHALL be built from the same plain elements and theme tokens the rest
of the transcript uses, consistent with the transcript being deliberately hand-rolled
rather than assembled from the component library used for the surrounding chrome.

#### Scenario: Choices are stacked, not flowed

- **WHEN** a question offering several choices is rendered
- **THEN** each choice SHALL occupy its own full-width row in a vertical stack

#### Scenario: A long description wraps inside the card

- **WHEN** a choice carries a description longer than the width of the transcript
- **THEN** that description SHALL wrap onto further lines within its row
- **AND** SHALL NOT be clipped at, or extend past, the edge of the card

#### Scenario: An unanswerable choice looks and behaves inert

- **WHEN** a question can no longer be answered
- **THEN** its choice rows SHALL be rendered in a visually distinct inert state
- **AND** SHALL NOT respond to the pointer

## MODIFIED Requirements

### Requirement: System tools get purpose-built cards through a renderer registry
The dashboard SHALL map a tool name to a presentation through a registry, and SHALL render every tool absent from that registry with the generic readable card. Adding a bespoke presentation SHALL therefore be an entry in that table plus one renderer, and SHALL NOT require changing how any other tool renders.

`spawn_subagent` and `prompt_player_agent` SHALL name the child agent they started and SHALL offer a control that opens the existing subagent output view on that child job. `prompt_player_agent` SHALL additionally name the seat it prompted. Where the child job cannot be identified — the launch failed, or its result was not the expected shape — the control SHALL be omitted rather than opening nothing.

`wait_for_subagent` SHALL show a running animation while the wait is outstanding, together with the child it is waiting on, and SHALL announce that state to assistive technology. Once the wait ends the animation SHALL be replaced by its outcome, distinguishing a collected report from an abandoned wait.

`load_skill` and `load_skill_reference` SHALL put the skill name — and the reference name where there is one — on the card header, and SHALL keep the loaded document behind the collapse with an indication of its size.

The control that opens a subagent SHALL be offered only where there is somewhere to open it, so a transcript rendered outside the Play workspace shows the card without a dead control.

A registry renderer MAY render no card at all, and SHALL do so only where another transcript row is already that exchange's representation. Rendering both would print the same content twice, which is the whole reason the exception exists rather than a matter of taste. Suppression SHALL NOT extend to an exchange that failed: where a tool's other representation is written only on success, the card is the sole place a failure is visible, so a failed exchange SHALL keep the generic readable card including its error surface.

`ask_user` SHALL be presented this way. Its exchange is represented by the question row the transcript renders from the durable question event, which shows the wording, the choices offered and the answer given, so no tool card SHALL be rendered for a successful or still-pending `ask_user` call. A failed `ask_user` call — arguments that did not validate, a call from a context with no user attached, or a question that was cancelled or could not be found — records no question event, so such a call SHALL render the generic readable card.

#### Scenario: A spawn offers a way into the subagent it started
- **WHEN** a `spawn_subagent` call has returned a child job id
- **THEN** the card SHALL name that child
- **AND** SHALL offer a control that opens the subagent output view on that child job

#### Scenario: A player prompt names its seat
- **WHEN** a `prompt_player_agent` call has been recorded for a seat
- **THEN** the card SHALL name that seat alongside the child agent it started

#### Scenario: An outstanding wait animates
- **WHEN** a `wait_for_subagent` call has no result yet
- **THEN** the card SHALL show a running animation naming the child being waited on
- **AND** SHALL expose that state as a live status to assistive technology

#### Scenario: A finished wait shows its outcome
- **WHEN** the `tool_result` for a `wait_for_subagent` call arrives
- **THEN** the card SHALL replace the animation with the outcome of the wait

#### Scenario: A skill load is named by its skill
- **WHEN** a `load_skill` call has been recorded
- **THEN** the card header SHALL show the skill's name and the size of the loaded document
- **AND** the document itself SHALL NOT be rendered until the card is expanded

#### Scenario: An unregistered tool still reads well
- **WHEN** a tool with no registry entry is called
- **THEN** the transcript SHALL render it with the generic readable card

#### Scenario: An answered question is not also printed as a tool card
- **WHEN** an `ask_user` call has been answered
- **THEN** the transcript SHALL render no tool card for it
- **AND** the question's wording SHALL appear only in the question row

#### Scenario: A pending question is not also printed as a tool card
- **WHEN** an `ask_user` call is still waiting for an answer
- **THEN** the transcript SHALL render no tool card for it

#### Scenario: A failed ask_user call is still visible
- **WHEN** an `ask_user` call returns an error, having recorded no question
- **THEN** the transcript SHALL render the generic readable card for it
- **AND** that card SHALL show that the exchange failed
