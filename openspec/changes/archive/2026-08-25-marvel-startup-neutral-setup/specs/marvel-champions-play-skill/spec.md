## ADDED Requirements

### Requirement: The Marvel harness reference uses the actual option argument names

When the session platform is `marvel-lcg`, the player skill's harness reference SHALL instruct the
agent to call `list_game_options(session_id, player_n)` and
`choose_game_option(session_id, player_n, option_id, targets, resources, prompt_id,
prompt_version)`. It SHALL name `player_n` as the neutral seat argument, require the prompt
identity returned by the preceding list call, state that option names are not identities, and direct
the agent to read the current option list before choosing. It SHALL not use the stale `player`
argument name.

#### Scenario: A Marvel player lists options for its own seat

- **WHEN** a player agent reads the Marvel harness recipe
- **THEN** the recipe SHALL show `list_game_options` with `session_id` and `player_n`
- **AND** it SHALL pass the agent's assigned neutral seat in `player_n`

#### Scenario: A Marvel player submits a selected option

- **WHEN** a player agent submits a legal choice
- **THEN** the recipe SHALL show `choose_game_option` with `player_n`, `option_id`, `targets`,
  `resources`, `prompt_id`, and `prompt_version`
- **AND** it SHALL not tell the agent to submit `player`

#### Scenario: A stale argument cannot be taught by the skill

- **WHEN** the generated option tool schema is compared with the Marvel harness reference
- **THEN** both SHALL use `player_n`
- **AND** a reference containing only `player` SHALL fail the skill/tool contract check

### Requirement: The player skill routes setup selection to the neutral catalog

The player-facing skill SHALL not promise a fixed Marvel hero or scenario. When a player agent is
given setup responsibility, it SHALL direct setup discovery to `list_game_setup_catalog` and SHALL
use the caller-provided typed scenario and hero-deck ids. It SHALL report missing setup data rather
than selecting the first catalog entry or relying on a hardcoded hero.

#### Scenario: A player follows a caller-selected hero

- **WHEN** a player prompt identifies a neutral seat and a selected hero-deck id
- **THEN** the skill SHALL preserve that selection when describing setup verification
- **AND** it SHALL instruct the agent to confirm the resulting state rather than assume a default

#### Scenario: The skill does not invent setup

- **WHEN** a player prompt omits its scenario or hero-deck selection
- **THEN** the skill SHALL instruct the agent to report the missing input
- **AND** it SHALL not instruct the agent to choose a fixed or first-listed hero
