## ADDED Requirements

### Requirement: Transcript re-render cost is bounded by what changed
Both dashboard transcripts SHALL bound the work of an update by what actually changed rather than by the length of the transcript, so the cost of one streamed token, one selection, or one search keystroke does not grow with the size of the session's history.

In the Play transcript, an arriving job event SHALL re-render only the job thread that event belongs to and, within it, only the blocks whose content changed. A settled response SHALL NOT be re-rendered — and in particular its markdown SHALL NOT be re-parsed — because a later job received a token. An update that changes no job SHALL re-render no block at all.

In the History transcript, moving the selection SHALL re-render only the row losing the selection and the row gaining it. A refresh that changes no event SHALL re-render no row. Every value handed to a row SHALL be referentially stable across renders that did not change it, including the empty verdict list, the default expand and reveal pulses, the restore callback and the board-action bundle; a row SHALL receive the current selection only when that selection is one of the row's own verdicts.

Achieving this SHALL NOT change what either transcript renders: the rendered output SHALL be identical before and after, and the transcript's scroll container SHALL keep mounting the full transcript so that the follow lock continues to work against real scroll geometry.

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
- **WHEN** a transcript is rendered for a session before and after this containment is applied
- **THEN** the rendered output SHALL be identical
