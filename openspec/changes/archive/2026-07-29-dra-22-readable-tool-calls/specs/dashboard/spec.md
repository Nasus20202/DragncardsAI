## ADDED Requirements

### Requirement: Tool invocations render as readable invocations
The Play transcript SHALL present a tool invocation as one card describing what was called, with what, and what came back — not as a serialised event payload.

A `tool_call` event and the `tool_result` event that answers it SHALL be paired by `tool_call_id` and rendered as a single item, so that calls issued in parallel and events interleaved between a call and its result still pair correctly. A call whose result has not arrived SHALL be shown as still running. A result with no call to pair to SHALL still be shown rather than dropped.

A collapsed card SHALL name the tool and SHALL summarise its arguments on one line. Arguments that are scalars SHALL be summarised by name and value; an argument that is an object or a list SHALL be summarised by its shape rather than by its contents, so the line stays readable regardless of what was passed. A call that failed SHALL be marked as failed without being expanded.

An expanded card SHALL list each argument by name beside its value, SHALL show the result, and SHALL state which server answered and which call it was. A call that carries no structured arguments — an older event, or the invalid-tool-call path — SHALL fall back to its recorded body text rather than showing nothing.

The cards SHALL reuse the transcript's existing card styling, so a tool card is visually of a piece with the reasoning and compaction blocks beside it.

#### Scenario: A call and its result are one card
- **WHEN** a job records a `tool_call` and the `tool_result` answering the same `tool_call_id`
- **THEN** the transcript SHALL render one card for the pair
- **AND** that card SHALL name the tool and summarise the call's arguments without being expanded

#### Scenario: Arguments are named, not serialised
- **WHEN** the reader expands a tool card
- **THEN** the transcript SHALL show each argument's name beside its value
- **AND** SHALL show the tool's result and which server answered the call

#### Scenario: An unanswered call reads as running
- **WHEN** a `tool_call` has been recorded and no matching `tool_result` has arrived
- **THEN** the transcript SHALL present the invocation as still running

#### Scenario: A failed call is visible without expanding
- **WHEN** a `tool_result` arrives with `is_error` set
- **THEN** the transcript SHALL mark the collapsed card as an error

#### Scenario: A result with no call is still shown
- **WHEN** a `tool_result` is present whose `tool_call` is not in the loaded events
- **THEN** the transcript SHALL still render that result

### Requirement: System tools get purpose-built cards through a renderer registry
The dashboard SHALL map a tool name to a presentation through a registry, and SHALL render every tool absent from that registry with the generic readable card. Adding a bespoke presentation SHALL therefore be an entry in that table plus one renderer, and SHALL NOT require changing how any other tool renders.

`spawn_subagent` and `prompt_player_agent` SHALL name the child agent they started and SHALL offer a control that opens the existing subagent output view on that child job. `prompt_player_agent` SHALL additionally name the seat it prompted. Where the child job cannot be identified — the launch failed, or its result was not the expected shape — the control SHALL be omitted rather than opening nothing.

`wait_for_subagent` SHALL show a running animation while the wait is outstanding, together with the child it is waiting on, and SHALL announce that state to assistive technology. Once the wait ends the animation SHALL be replaced by its outcome, distinguishing a collected report from an abandoned wait.

`load_skill` and `load_skill_reference` SHALL put the skill name — and the reference name where there is one — on the card header, and SHALL keep the loaded document behind the collapse with an indication of its size.

The control that opens a subagent SHALL be offered only where there is somewhere to open it, so a transcript rendered outside the Play workspace shows the card without a dead control.

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

### Requirement: Displayed tool arguments and results are redacted
The dashboard SHALL redact credential-shaped text from every tool argument value, every tool result string, and every provenance value it displays, using the same shapes the eval service redacts from stored error detail: named credential fields and headers with a `:` or `=` separator, bare bearer tokens, and bare provider key literals. Redaction SHALL happen before any length cap is applied, and a value cut short SHALL NOT expose the leading part of a credential the cap fell inside.

Because a card displays an argument's name and its value as two separate pieces of text, a pattern that recognises a credential by the field name in front of it cannot fire on the value. An argument whose own *name* names a credential SHALL therefore have its value replaced entirely, in the collapsed summary, in the expanded row, and in the full text behind "show all" — there SHALL be no path from such an argument to its value.

The MCP server a call was routed to SHALL be redacted before being displayed, because a registered server URL can carry a token in its path or query.

Every argument and result SHALL be rendered as text. The dashboard SHALL NOT interpret model-supplied or server-supplied tool content as markup, and SHALL NOT interpolate it into anything executable.

A child job id read out of a tool argument SHALL be accepted only when it is shaped like a job identifier, because it is written by the model and the view it opens interpolates it into a request path. An identifier that is not SHALL be treated as no reference at all, so no control is offered.

#### Scenario: A credential in an error result is not shown
- **WHEN** a tool result carries a gateway error whose text contains an API key
- **THEN** the transcript SHALL show the error with the credential replaced
- **AND** the credential SHALL NOT appear anywhere in the rendered document

#### Scenario: A credential past the displayed window is still redacted
- **WHEN** a displayed value is capped and a credential sits beyond the cap but within the redaction window
- **THEN** the credential SHALL be replaced rather than partially shown

#### Scenario: Prose mentioning a secret is left intact
- **WHEN** a tool result contains the word "secret" in ordinary prose with no credential after it
- **THEN** the text SHALL be shown unchanged

#### Scenario: An argument named as a credential never shows its value
- **WHEN** a tool is called with an argument named `api_key`, `password`, `token` or any other credential name
- **THEN** the value SHALL be shown as redacted in the collapsed summary and in the expanded row
- **AND** no control SHALL be offered that reveals the value

#### Scenario: A token in a registered server URL is not shown
- **WHEN** a call was routed to an MCP server whose URL carries a credential
- **THEN** the card's provenance line SHALL show that URL with the credential replaced

#### Scenario: A forged child job id offers no control
- **WHEN** a `wait_for_subagent` argument names a child job id containing path or query syntax
- **THEN** the dashboard SHALL treat it as identifying no subagent
- **AND** SHALL NOT offer a control that would request it

## MODIFIED Requirements

### Requirement: Transcript re-render cost is bounded by what changed
Both dashboard transcripts SHALL bound the work of an update by what actually changed rather than by the length of the transcript, so the cost of one streamed token, one selection, or one search keystroke does not grow with the size of the session's history.

In the Play transcript, an arriving job event SHALL re-render only the job thread that event belongs to and, within it, only the blocks whose content changed. A settled response SHALL NOT be re-rendered — and in particular its markdown SHALL NOT be re-parsed — because a later job received a token. An update that changes no job SHALL re-render no block at all.

In the History transcript, moving the selection SHALL re-render only the row losing the selection and the row gaining it. A refresh that changes no event SHALL re-render no row. Every value handed to a row SHALL be referentially stable across renders that did not change it, including the empty verdict list, the default expand and reveal pulses, the restore callback and the board-action bundle; a row SHALL receive the current selection only when that selection is one of the row's own verdicts.

The cost of one transcript block SHALL likewise be bounded by what that block displays rather than by the size of the payload behind it. A collapsed tool card SHALL NOT serialise the call's arguments or the result's body: every value it shows SHALL be produced by a formatter that stops reading the payload once it has enough characters for the line, so a call carrying a full board state or a card list costs the same to present as a two-argument call. The full text of an argument or a result SHALL be produced only inside an expanded card, and only when the reader asks for the whole of it; an expanded card SHALL cap what it renders and offer the remainder on request, so opening one cannot stretch the transcript to the height of its payload.

Achieving this containment SHALL NOT change what a transcript renders: any given transcript SHALL render identically with the containment applied and without it, and the transcript's scroll container SHALL keep mounting the full transcript so that the follow lock continues to work against real scroll geometry.

#### Scenario: A streamed token leaves settled responses alone
- **WHEN** a job event arrives for the streaming job in a session that already holds several completed jobs
- **THEN** the dashboard SHALL re-render only that job's thread
- **AND** SHALL NOT re-render or re-parse the markdown of any earlier completed response

#### Scenario: An update that changed nothing renders nothing
- **WHEN** the Play transcript re-renders with a job list whose jobs are all unchanged
- **THEN** the dashboard SHALL NOT re-render any transcript block

#### Scenario: Moving the History selection touches two rows
- **WHEN** the selected event changes in the History transcript
- **THEN** the dashboard SHALL re-render only the previously selected row and the newly selected row

#### Scenario: A History refresh that changed nothing renders no rows
- **WHEN** the History transcript re-renders with the same events and the same selection
- **THEN** the dashboard SHALL NOT re-render any event row

#### Scenario: Rendered output is unchanged
- **WHEN** a transcript is rendered for a session with and without this containment
- **THEN** the rendered output SHALL be identical

#### Scenario: A huge tool payload does not reach a collapsed card
- **WHEN** a tool call carries a large argument or its result carries a large body
- **THEN** the collapsed card SHALL remain the size of a header line
- **AND** SHALL NOT contain the payload

#### Scenario: A streamed token rebuilds no settled tool card
- **WHEN** a job event arrives for the streaming job in a session whose earlier jobs hold completed tool exchanges
- **THEN** the dashboard SHALL NOT rebuild the presentation of any of those earlier tool exchanges
