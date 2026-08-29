## MODIFIED Requirements

### Requirement: Game action execution
The DragnCards backend SHALL accept game actions submitted via the room channel and apply them to the game state.

For a `draw_boost` action, the backend workflow SHALL mark the drawn encounter card as a boost while it is used during villain activation without making its identity visible to an unauthorized reader. When the DragnCards villain phase ends, the workflow SHALL identify every card whose authoritative engine state marks it as a boost, clear that transient marker and state, and move the card to the shared encounter discard before advancing to the next player phase. The workflow SHALL NOT select a card from a collapsed hidden count, a stack position, or an identity supplied by the caller, and SHALL NOT log or return the hidden card's name or identifier as part of cleanup.

#### Scenario: Submit a valid game action
- **WHEN** the Game Service pushes a `game_action` event on the room channel with a DragnLang payload `{"action": [...], "options": {"description": "..."}, "timestamp": <ms>`
- **THEN** the DragnCards backend SHALL apply the action to the game state and reply with `phx_reply` status `"ok"`

#### Scenario: State update broadcast after action
- **WHEN** a game action is applied
- **THEN** the DragnCards backend SHALL broadcast a `state_update` event on the room channel indicating the game state has changed

#### Scenario: Invalid or rejected action
- **WHEN** the Game Service pushes a `game_action` event that the DragnCards engine cannot apply
- **THEN** the DragnCards backend SHALL reply with `phx_reply` status `"error"` and a response payload describing the failure

#### Scenario: Draw boost remains hidden while active
- **WHEN** a valid `draw_boost` action moves an encounter card into a player's engaged zone for villain activation
- **THEN** the card SHALL remain represented to an unauthorized state reader only as a hidden count
- **AND** the engine SHALL retain an authoritative boost marker for the cleanup workflow

#### Scenario: Villain end phase authoritatively cleans boost cards
- **WHEN** the DragnCards villain end-phase action runs after one or more boost cards were drawn
- **THEN** every card with the engine's boost marker SHALL be moved to the shared encounter discard and have its boost marker, rotation, and transient tokens cleared before the next player phase begins
- **AND** the cleanup SHALL use the marked card records rather than a hidden count or stack position
- **AND** the action log and response SHALL NOT reveal a cleaned card's name or identifier

#### Scenario: Villain end phase tolerates an already-discarded boost
- **WHEN** a boost-marked card is already in the shared encounter discard when villain end phase runs
- **THEN** the workflow SHALL clear the stale boost marker and transient state without failing or selecting another card by position
- **AND** the action SHALL not reveal the card's identity
