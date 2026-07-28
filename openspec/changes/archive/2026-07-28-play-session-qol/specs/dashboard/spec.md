## MODIFIED Requirements

### Requirement: Session list removal and terminated-session hiding
The dashboard SHALL provide a per-session removal control in the Play session list that permanently deletes the session through the agent-orchestrator session deletion endpoint, and SHALL hide terminated sessions from the session list by default.

Removal SHALL delete rather than terminate: the session and everything recorded under it are gone afterwards, so a removed session SHALL NOT reappear in the session list on a later load.

The removal control SHALL require an explicit confirmation before deleting. That confirmation SHALL be presented as an in-application modal dialog rather than a browser-native confirmation prompt. The dialog SHALL name the session being deleted, SHALL describe what deletion actually does — the session's settings and full transcript are removed permanently, and any running work is cancelled first — SHALL offer a cancel action alongside a danger-styled confirm action, and SHALL leave the removal trigger in the session list unchanged.

After a successful deletion the dashboard SHALL drop the session from the list and, when the deleted session was the selected one, SHALL select the next session the list shows, or no session when none remain.

#### Scenario: Remove a session from the list
- **WHEN** a user activates the per-session removal control for a session in the Play session list and confirms the action
- **THEN** the dashboard SHALL delete that session through the agent-orchestrator session deletion endpoint
- **AND** the deleted session SHALL no longer appear in the session list

#### Scenario: Deleted sessions do not come back
- **WHEN** the session list is reloaded after a session was deleted
- **THEN** that session SHALL NOT be listed, because it no longer exists rather than being hidden

#### Scenario: Terminated sessions hidden by default
- **WHEN** the Play session list renders sessions whose status is terminated
- **THEN** the dashboard SHALL exclude those terminated sessions from the list by default

#### Scenario: Removal requires confirmation
- **WHEN** a user activates the removal control but does not confirm the destructive action
- **THEN** the dashboard SHALL NOT delete the session

#### Scenario: Confirmation dialog names the session at risk
- **WHEN** a user activates the removal control for a session
- **THEN** the dashboard SHALL open a modal confirmation dialog that names that session, states that its settings and transcript are deleted permanently, and warns the action cannot be undone
- **AND** SHALL NOT have deleted the session at the point the dialog appears

#### Scenario: Dismissing the confirmation cancels the removal
- **WHEN** a user cancels or dismisses the removal confirmation dialog
- **THEN** the dialog SHALL close, the session SHALL remain in the session list, and no deletion request SHALL be sent

#### Scenario: Selection moves on after deleting the selected session
- **WHEN** the deleted session was the selected one
- **THEN** the dashboard SHALL select the next session the list shows, or no session at all when the list is empty

### Requirement: New sessions preserve last-used settings
The dashboard SHALL create new Play sessions seeded with the user's last-used settings — provider, model, reasoning enabled state and effort, selected skills, recent message and tool-exchange limits, and advanced/MCP option selections — instead of resetting every field to configuration defaults.

Those settings SHALL survive a page reload: the configuration the user last committed SHALL be remembered client-side, per browser, and used to seed the draft on a later visit. Only committed configurations SHALL be remembered — creating a session, saving a session's configuration, or changing the provider/model that is committed immediately — so that a partially edited field is never carried forward. The session name SHALL never be carried forward; each new session gets a freshly generated one.

The remembered configuration SHALL NOT override the settings of a session the user opens: loading a session SHALL replace the draft with that session's own configuration.

The dashboard SHALL fall back to configuration defaults only when there is no prior draft, remembered configuration, or session to copy settings from, and SHALL treat an unreadable or unwritable client-side store as having no remembered configuration rather than as an error.

#### Scenario: New session inherits previous settings
- **WHEN** a user has configured a session's provider, model, reasoning, skills, and replay limits and then creates a new session
- **THEN** the dashboard SHALL seed the new session with those last-used settings rather than the configuration defaults

#### Scenario: Settings survive a reload
- **WHEN** a user reloads the dashboard with no session selected after having committed a configuration earlier
- **THEN** the draft SHALL be seeded from that remembered configuration rather than from the configuration defaults, with a freshly generated session name

#### Scenario: An opened session keeps its own settings
- **WHEN** a user opens an existing session while a different configuration is remembered
- **THEN** the draft SHALL show that session's own provider, model, reasoning, and skills

#### Scenario: First session falls back to defaults
- **WHEN** a user creates a new session and there is no prior draft, remembered configuration, or session to copy settings from
- **THEN** the dashboard SHALL seed the new session from the configuration defaults

### Requirement: Transcript scroll lock
The dashboard transcript SHALL follow new content only while the scroll lock is engaged, and SHALL start engaged so that the newest output is visible by default. Following SHALL scroll to the true bottom of the transcript rather than to a position short of it.

A user gesture that moves away from the newest output SHALL release the lock immediately, even while output is streaming: an upward wheel, a key that scrolls upwards, or a touch drag away from the bottom. Releasing SHALL NOT be defeated by the dashboard's own auto-follow scrolling; a release SHALL cancel any in-flight programmatic scroll and leave the viewport where the user put it, and subsequent content SHALL NOT move it.

While the lock is released the dashboard SHALL present a control that re-engages the lock and scrolls to the newest content. Scrolling back to the bottom SHALL also re-engage it.

The dashboard SHALL keep the lock honest as the transcript resizes for reasons the arriving content does not describe: while engaged, content that grows after the fact SHALL still be followed; while released, content that shrinks until it fits within one viewport SHALL re-engage the lock, so the re-engage control is never offered when there is nothing to scroll.

#### Scenario: Follow new content by default
- **WHEN** new transcript content arrives and the user has not scrolled away from the bottom
- **THEN** the dashboard SHALL scroll the transcript to the newest content, and SHALL NOT offer the re-engage control

#### Scenario: Scrolling up during streaming releases the follow
- **WHEN** the user scrolls the transcript upwards with the wheel, keyboard, or a touch drag while the agent is still writing
- **THEN** the dashboard SHALL stop following, SHALL leave the viewport where the user scrolled to as further content arrives, and SHALL display the re-engage control

#### Scenario: The re-engage control resumes following
- **WHEN** the user activates the re-engage control
- **THEN** the dashboard SHALL scroll the transcript to the newest content and follow new content again

#### Scenario: Returning to the bottom resumes following
- **WHEN** the user scrolls the transcript back to the bottom
- **THEN** the dashboard SHALL follow new content again and SHALL withdraw the re-engage control

#### Scenario: Nothing to scroll withdraws the control
- **WHEN** the transcript shrinks until it fits within one viewport while the lock is released
- **THEN** the dashboard SHALL re-engage the lock rather than leaving the re-engage control on screen

### Requirement: Resilient provider and model loading
The dashboard initial load SHALL tolerate a slow or failed providers fetch and unusable providers without blocking or breaking the rest of the dashboard. A failure in any single initial-load call SHALL degrade gracefully rather than failing the whole dashboard.

The provider catalog SHALL be loaded off the dashboard's blocking initial-load path. The workspace SHALL render as soon as the dashboard configuration, skills, and sessions have resolved, and SHALL NOT wait for the provider catalog before its first paint. The dashboard configuration SHALL remain the only initial-load call whose failure is fatal.

A provider SHALL be treated as usable only when it both reports itself available and offers at least one model, because a provider whose credentials are missing answers the model listing successfully with an empty list. The non-blocking notice SHALL name every provider that is not usable by that measure, and SHALL make clear that the remaining providers still work.

A provider that offers no models SHALL be labelled as offering none in the provider selector and SHALL NOT be selectable, so that selecting it cannot leave the user on a disabled model selector holding a model from a different provider. A session already configured for such a provider SHALL still display that provider and SHALL remain able to move to a usable one.

When the provider catalog arrives, the dashboard SHALL point the selectors at a provider the user can actually use, clamping the model to one that provider offers. This SHALL NOT overwrite a provider/model selection that a loaded session has committed. An empty catalog SHALL be treated as no information about the drafted provider, and SHALL NOT reset a carried provider or model.

#### Scenario: Workspace renders before the provider catalog resolves
- **WHEN** the dashboard loads and the providers fetch is still in flight
- **THEN** the dashboard SHALL render the workspace and report a ready status without waiting for the providers fetch to complete

#### Scenario: Late-arriving catalog is applied
- **WHEN** the providers fetch resolves after the workspace has already rendered
- **THEN** the dashboard SHALL apply the catalog, pointing the provider and model selectors at a usable provider and updating the notice

#### Scenario: Late-arriving catalog does not clobber a session's selection
- **WHEN** the providers fetch resolves after a loaded session has committed its own model
- **THEN** the dashboard SHALL leave that selection unchanged

#### Scenario: One failed load call degrades gracefully
- **WHEN** the providers fetch (or any single initial-load call) fails or is slow during dashboard load
- **THEN** the dashboard SHALL still load the remaining data and SHALL NOT present a single fatal error that blocks the workspace

#### Scenario: Providers without models are named and not selectable
- **WHEN** one or more providers report themselves available but offer no models
- **THEN** the dashboard SHALL name them in a non-blocking notice, SHALL label them as offering no models in the provider selector, and SHALL NOT allow them to be selected

#### Scenario: Model selection keeps working on usable providers
- **WHEN** some providers offer no models but at least one provider does
- **THEN** the dashboard SHALL point the selectors at a usable provider and SHALL allow the user to change the model on it

#### Scenario: A degraded catalog does not reset a carried selection
- **WHEN** a new session is created while the provider catalog is empty because it failed to load
- **THEN** the dashboard SHALL carry the last-used provider and model forward rather than resetting them to the configuration defaults
