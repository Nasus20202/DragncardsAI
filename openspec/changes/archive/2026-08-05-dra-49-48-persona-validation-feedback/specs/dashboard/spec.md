## MODIFIED Requirements

### Requirement: Persona editor
The dashboard SHALL provide a dedicated page for authoring agent personas, reachable from the application shell's navigation, listing the personas that exist and letting a user create, edit, and delete one. The editor SHALL expose every field a persona carries: name, display name, description, system prompt, provider, model, reasoning, skill selection, and tool allowlist.

The editor SHALL be built from the shared field components the existing configuration panels use, so a new surface renders the same controls rather than hand-rolled equivalents, and SHALL NOT change the appearance of any existing panel.

The editor SHALL show the persona prompt's length against its limit while the user types, and SHALL refuse a save that would be rejected for exceeding it, so the bound is visible before the request rather than only in an error.

Every reason a draft cannot be saved SHALL be stated to the user in the editor, next to the field that causes it, rather than being expressed only as an unavailable control. A reason SHALL be attributed to a single field, and the field's control SHALL be marked invalid and associated with its message for assistive technology, so the reason is not carried by colour alone. The messages SHALL appear once the user has edited the draft or attempted a save, so an untouched new-persona form is not presented as already wrong.

A press of the save control that is refused SHALL additionally state its reason beside that control, associated with the control for assistive technology, and SHALL withdraw that statement once the draft can be saved. Every field a reason belongs to is a scroll above the control on this form, so a refused press SHALL NOT be indistinguishable from a press that did nothing.

The editor SHALL NOT express a draft's validity through the save control's disabled state. The save control SHALL be unavailable only while a request the editor issued is in flight, and SHALL otherwise be pressable regardless of the draft's validity; a press with an invalid draft SHALL state the reason and SHALL NOT submit the draft to the agent-orchestrator. This keeps a validity-derived disabled attribute out of the server-rendered markup entirely: an attribute that is never emitted cannot be disagreed about by the hydrating browser, and React does not patch up a mismatch on it — it leaves the live control's disabled state diverged from what the component rendered.

An empty persona list SHALL be stated as such rather than rendering an empty container, and a failed load or save SHALL surface the orchestrator's message rather than failing silently.

#### Scenario: Personas are listed
- **WHEN** a user opens the personas page and personas exist
- **THEN** the dashboard SHALL list them by name with their descriptions

#### Scenario: Empty state is explicit
- **WHEN** a user opens the personas page and no personas exist
- **THEN** the dashboard SHALL state that no personas are defined

#### Scenario: A persona is created
- **WHEN** a user fills in a name and a system prompt and saves
- **THEN** the dashboard SHALL submit the persona to the agent-orchestrator and show it in the list

#### Scenario: A persona is edited
- **WHEN** a user selects an existing persona
- **THEN** the form SHALL be populated from the stored persona
- **AND** saving SHALL submit the edited values under the same name

#### Scenario: A persona is deleted
- **WHEN** a user deletes a persona
- **THEN** the dashboard SHALL submit the deletion and remove it from the list

#### Scenario: Prompt length is bounded in the UI
- **WHEN** a user types a system prompt longer than the permitted length
- **THEN** the dashboard SHALL show at the system prompt field that the limit is exceeded
- **AND** SHALL NOT submit the persona to the agent-orchestrator

#### Scenario: A missing name is stated at the name field
- **WHEN** a user attempts to save a new persona whose name is empty
- **THEN** the dashboard SHALL show at the name field that a persona needs a name
- **AND** SHALL NOT submit the persona to the agent-orchestrator

#### Scenario: A malformed name is stated at the name field
- **WHEN** a user types a persona name that is not a lowercase slug
- **THEN** the dashboard SHALL show at the name field which characters a name may contain

#### Scenario: A missing system prompt is stated at the prompt field
- **WHEN** a user has named a persona but left its system prompt empty
- **THEN** the dashboard SHALL show at the system prompt field that a persona needs one

#### Scenario: Two problems are stated at their own fields
- **WHEN** a draft has both a malformed name and an empty system prompt
- **THEN** the dashboard SHALL show the name's problem at the name field and the prompt's problem at the prompt field, rather than only the first of the two

#### Scenario: A refused press of save says why beside the save control
- **WHEN** a user presses the save control with a draft that cannot be saved
- **THEN** the dashboard SHALL state the reason beside that control and associate it with the control for assistive technology
- **AND** SHALL withdraw the statement once the draft can be saved

#### Scenario: A problem is reported to assistive technology
- **WHEN** the dashboard shows a field's validation problem
- **THEN** that field's control SHALL be marked invalid and SHALL be associated with the message, so the problem is conveyed without relying on its colour

#### Scenario: An untouched new-persona form is not pre-marked as wrong
- **WHEN** a user opens the personas page and has neither edited the draft nor attempted a save
- **THEN** the dashboard SHALL show no validation messages

#### Scenario: The edit path reports the same problems
- **WHEN** a user loads an existing persona for editing and clears its system prompt
- **THEN** the dashboard SHALL show at the system prompt field that a persona needs one, as it does when creating one

#### Scenario: The save control does not encode validity
- **WHEN** the personas page is rendered on the server, or a user views a draft that cannot yet be saved
- **THEN** the save control SHALL NOT be disabled on account of the draft's validity
- **AND** the server-rendered save control SHALL carry no disabled attribute for the browser to hydrate against

#### Scenario: A rejected save is reported
- **WHEN** the agent-orchestrator rejects a persona — for instance because it names an unknown skill
- **THEN** the dashboard SHALL display the returned message rather than discarding it
