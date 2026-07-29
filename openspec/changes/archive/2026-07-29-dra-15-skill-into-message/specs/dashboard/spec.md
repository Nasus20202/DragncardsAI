## MODIFIED Requirements

### Requirement: Attach session skills from the chat composer
The dashboard SHALL let the user attach a skill to the selected Play session from the chat composer, without opening the settings panel. Typing the mention trigger `@` in the prompt input SHALL open a picker listing the skills available to that session, and choosing one SHALL attach that skill to the session.

The picker SHALL narrow its list as the user types after the `@`, using the same case-insensitive substring match the shared searchable model picker uses, so the two filter alike. It SHALL offer every skill available to the session, including skills already attached to it, because a mention loads that skill into the message being written — worth doing again on a later turn even when the session attachment is already in place. It SHALL be dismissable with `Escape`, and while it is open `Enter` SHALL choose the highlighted skill instead of submitting the message.

An `@` SHALL only start a mention at the beginning of the message or after whitespace, and a mention SHALL end at the first whitespace, so an email address or an `@` inside a word does not open the picker.

Choosing a skill SHALL complete the partial `@…` token into the full `@<skill-name>` token followed by a single space, leaving the caret after it. The mention SHALL remain in the message text and in the message the user sends, because the mention is what loads that skill into the turn.

#### Scenario: Typing the mention trigger opens the skill picker
- **WHEN** a user with an active session types `@` in the prompt input
- **THEN** the dashboard SHALL show a picker listing the skills available to that session

#### Scenario: Mention query filters the picker
- **WHEN** the user continues typing after the `@`
- **THEN** the picker SHALL list only skills whose name contains the typed text, case-insensitively

#### Scenario: Choosing a skill attaches it and completes the token
- **WHEN** the user chooses a skill from the picker
- **THEN** the dashboard SHALL attach that skill to the selected session
- **AND** SHALL replace the partial `@…` token with `@<skill-name>` followed by a space
- **AND** SHALL leave the caret directly after the completed token

#### Scenario: Enter chooses from the picker instead of sending
- **WHEN** the picker is open and the user presses `Enter`
- **THEN** the dashboard SHALL attach the highlighted skill and SHALL NOT submit the message

#### Scenario: Escape dismisses the picker
- **WHEN** the picker is open and the user presses `Escape`
- **THEN** the dashboard SHALL close the picker and leave the prompt text unchanged

#### Scenario: An @ inside a word does not open the picker
- **WHEN** the prompt text contains an `@` that is neither at the start of the message nor preceded by whitespace
- **THEN** the dashboard SHALL NOT open the picker

#### Scenario: An already-attached skill is still offered
- **WHEN** the picker opens for a session that already has a skill attached
- **THEN** that skill SHALL still appear among the picker's options, so it can be loaded into this message

#### Scenario: No picker without an active session
- **WHEN** no session is selected, or the selected session is not active
- **THEN** typing `@` SHALL NOT open the picker

## ADDED Requirements

### Requirement: A mentioned skill is loaded into the message it was typed in
Submitting a prompt SHALL name the skills the message mentions, so the agent-orchestrator loads their instructions into that turn. A name SHALL be sent only when the message contains it as a mention token — an `@` at the start of the message or after whitespace, ending at the first whitespace — and only when it matches a skill currently assigned to the selected session, so ordinary text containing an `@` never loads anything.

The same skill mentioned more than once in one message SHALL be named once.

The message text sent SHALL be exactly what the user typed, mention tokens included. The dashboard SHALL NOT expand skill content into the message text itself, because skill content stays server-side.

A message with no mentions SHALL submit exactly as it did before, naming no skills.

#### Scenario: Mentioned skill is named on submission
- **WHEN** the user sends a message containing `@<skill-name>` for a skill assigned to the session
- **THEN** the dashboard SHALL submit the prompt naming that skill as loaded into the message
- **AND** the submitted prompt text SHALL still contain the mention token

#### Scenario: Text that only looks like a mention loads nothing
- **WHEN** the message contains an `@` token that matches no skill assigned to the session
- **THEN** the dashboard SHALL submit the prompt naming no skills

#### Scenario: A repeated mention is named once
- **WHEN** the message mentions the same skill twice
- **THEN** the dashboard SHALL name that skill exactly once on submission

#### Scenario: A message without mentions is unchanged
- **WHEN** the user sends a message containing no mention token
- **THEN** the dashboard SHALL submit the prompt with no skills named
