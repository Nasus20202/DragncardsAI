## ADDED Requirements

### Requirement: Attach session skills from the chat composer
The dashboard SHALL let the user attach a skill to the selected Play session from the chat composer, without opening the settings panel. Typing the mention trigger `@` in the prompt input SHALL open a picker listing the skills available to that session, and choosing one SHALL attach that skill to the session.

The picker SHALL narrow its list as the user types after the `@`, using the same case-insensitive substring match the shared searchable model picker uses, so the two filter alike. It SHALL offer only skills not already attached, because an attached skill is already shown as a chip on the composer. It SHALL be dismissable with `Escape`, and while it is open `Enter` SHALL choose the highlighted skill instead of submitting the message.

An `@` SHALL only start a mention at the beginning of the message or after whitespace, and a mention SHALL end at the first whitespace, so an email address or an `@` inside a word does not open the picker.

Choosing a skill SHALL remove the `@…` token from the message text, because the attached skill is represented by a chip on the composer rather than by text in the prompt. The message the user sends SHALL NOT contain the mention token.

#### Scenario: Typing the mention trigger opens the skill picker
- **WHEN** a user with an active session types `@` in the prompt input
- **THEN** the dashboard SHALL show a picker listing the skills available to that session

#### Scenario: Mention query filters the picker
- **WHEN** the user continues typing after the `@`
- **THEN** the picker SHALL list only skills whose name contains the typed text, case-insensitively

#### Scenario: Choosing a skill attaches it and clears the token
- **WHEN** the user chooses a skill from the picker
- **THEN** the dashboard SHALL attach that skill to the selected session
- **AND** SHALL remove the `@…` token from the prompt text

#### Scenario: Enter chooses from the picker instead of sending
- **WHEN** the picker is open and the user presses `Enter`
- **THEN** the dashboard SHALL attach the highlighted skill and SHALL NOT submit the message

#### Scenario: Escape dismisses the picker
- **WHEN** the picker is open and the user presses `Escape`
- **THEN** the dashboard SHALL close the picker and leave the prompt text unchanged

#### Scenario: An @ inside a word does not open the picker
- **WHEN** the prompt text contains an `@` that is neither at the start of the message nor preceded by whitespace
- **THEN** the dashboard SHALL NOT open the picker

#### Scenario: Already-attached skills are not offered again
- **WHEN** the picker opens for a session that already has a skill attached
- **THEN** that skill SHALL NOT appear among the picker's options

#### Scenario: No picker without an active session
- **WHEN** no session is selected, or the selected session is not active
- **THEN** typing `@` SHALL NOT open the picker

### Requirement: Attached skills are shown and removable on the composer
The composer SHALL display the skills currently attached to the selected session as chips, each carrying a control that detaches that skill from the session. Detaching from a chip SHALL use the same session skill assignment that the settings panel's skill toggles use.

The chip row SHALL render only when at least one skill is attached, so a session with no skills shows an unchanged composer.

#### Scenario: Attached skill appears as a chip
- **WHEN** a session has a skill attached
- **THEN** the composer SHALL render a chip naming that skill

#### Scenario: Chip detaches the skill
- **WHEN** the user activates a chip's remove control
- **THEN** the dashboard SHALL detach that skill from the session

#### Scenario: No chip row without attached skills
- **WHEN** the selected session has no skills attached
- **THEN** the composer SHALL NOT render a chip row

### Requirement: Composer and settings panel share one skill assignment
The composer's skill chips and the settings panel's skill toggles SHALL read the same session skill value, so a skill attached from the composer is shown as enabled in the settings panel and a skill enabled in the settings panel is shown as a chip on the composer, with no separate composer-only state.

Attaching or detaching from the composer SHALL persist through the agent-orchestrator's session skill endpoints immediately, in the way MCP toggles already do, rather than waiting for the settings panel's Save. A subsequent Save from the settings panel SHALL therefore find nothing to change for that skill.

Attaching or detaching one skill from the composer SHALL NOT discard unsaved skill edits made in the settings panel for other skills, because only the mentioned skill's membership changes.

#### Scenario: Skill attached from chat shows as enabled in settings
- **WHEN** the user attaches a skill through the composer's mention picker
- **THEN** the settings panel SHALL show that skill's toggle as enabled

#### Scenario: Skill enabled in settings shows as a composer chip
- **WHEN** the user enables a skill in the settings panel's skill toggle list
- **THEN** the composer SHALL render a chip for that skill

#### Scenario: Attaching from chat persists immediately
- **WHEN** the user attaches a skill through the composer
- **THEN** the dashboard SHALL call the agent-orchestrator's add-skill endpoint for that session without waiting for a Save

#### Scenario: Detaching from chat persists immediately
- **WHEN** the user detaches a skill from a composer chip
- **THEN** the dashboard SHALL call the agent-orchestrator's remove-skill endpoint for that session without waiting for a Save

#### Scenario: Composer attachment reports failures
- **WHEN** the agent-orchestrator rejects an attach or detach requested from the composer
- **THEN** the dashboard SHALL surface the error and SHALL NOT show the skill as attached
