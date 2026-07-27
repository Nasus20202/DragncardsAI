## MODIFIED Requirements

### Requirement: Dashboard code quality
The dashboard SHALL pass ESLint and TypeScript checks with no errors, using HeroUI components for all controls, ES module imports at the top of each file only, and no inline type imports.

Every interactive control and stateful visual widget rendered by the dashboard SHALL be a Hero UI component rather than a raw HTML element or a bespoke re-implementation. Specifically, the dashboard SHALL use `Button` for all activatable controls, `RadioGroup`/`Radio`, `Checkbox`, `Select`, `SearchField`, and `TextField` with `Input`/`TextArea` for all form fields, `Table` for tabular data, `Modal` and `Drawer` for all overlays, and `Card`, `Alert`, `Chip`, `Spinner`, and `ProgressBar` for containers, status banners, badges, loading indicators, and progress meters. Non-interactive semantic markup (`div`, `p`, headings, lists, `iframe`) MAY remain plain HTML.

#### Scenario: Lint and typecheck pass
- **WHEN** `pnpm lint` and `pnpm typecheck` are run against the dashboard source
- **THEN** both SHALL exit with no errors

#### Scenario: No raw interactive elements remain
- **WHEN** the dashboard's `app/` and `features/` sources are searched for `<button`, `<input`, `<select`, `<textarea`, or `<table` outside of test files
- **THEN** no match SHALL be found, because each is rendered through its Hero UI equivalent

#### Scenario: Overlays are Hero UI overlays
- **WHEN** the dashboard opens the subagent output view, the delete-history confirmation, or any right-side panel (evaluations queue, player scorecard, Evaluate)
- **THEN** the overlay SHALL be rendered with the Hero UI `Modal` or `Drawer` family, providing a focus trap, Esc-to-close, and dismiss-on-outside-interaction

#### Scenario: Status feedback uses Hero UI Alert
- **WHEN** the dashboard reports an error, warning, or success outcome inline (load failures, restore outcomes, evaluation enqueue confirmations, partial OpenAPI loads)
- **THEN** the message SHALL be rendered with a Hero UI `Alert` carrying the matching `status`, and SHALL keep its `alert`/`status` ARIA role

### Requirement: Context health indicator
The dashboard UI SHALL display a context health indicator for the active session. The indicator SHALL show: a token usage progress bar, usage percentage, `tokens_used` / `context_window_size`, compaction count, and last-compacted timestamp (or "Never").

The dashboard SHALL present context usage as an estimate of the next orchestrator model request envelope, not as cumulative historical job usage.

The indicator SHALL update by re-fetching `GET /sessions/{session_id}/context` after each of the following events:
- A job completes, fails, or is cancelled
- A compaction fires
- The user saves session configuration, including model, skill, MCP, or replay-limit changes

The usage meter SHALL be rendered with the Hero UI `ProgressBar` component and SHALL expose `data-value` (the integer usage percentage) and `data-color` so the usage band is assertable. The band SHALL follow the usage ratio:
- Below 70%: `default` (neutral)
- 70-85%: `warning` (amber)
- Above 85%: `danger` (red)

#### Scenario: Indicator shown for active session
- **WHEN** a session is active in the dashboard
- **THEN** the context health indicator SHALL be visible with all fields populated

#### Scenario: Usage below the warning band
- **WHEN** context usage is below 70 percent
- **THEN** the progress meter SHALL report `data-color="default"`

#### Scenario: Usage in the warning band
- **WHEN** context usage is at or above 70 percent and below 85 percent
- **THEN** the progress meter SHALL report `data-color="warning"`

#### Scenario: Indicator color reflects usage level
- **WHEN** `usage_ratio` exceeds 0.85
- **THEN** the progress meter SHALL report `data-color="danger"` and render in red

#### Scenario: Indicator updates after compaction
- **WHEN** a compaction completes (manual or auto)
- **THEN** the indicator SHALL refresh and reflect reduced `tokens_used` and incremented `compaction_count`

#### Scenario: Indicator refreshes after configuration save
- **WHEN** the user saves session configuration
- **THEN** the context health indicator SHALL re-fetch `GET /sessions/{session_id}/context` immediately after the save completes successfully
- **THEN** the displayed token estimate SHALL reflect the updated system prompt, tool definitions, and replay window resulting from the new configuration

#### Scenario: Multi-turn memory disabled
- **WHEN** `multi_turn_memory` is `false` for the active session
- **THEN** the indicator SHALL render no progress meter, SHALL display a "Memory off" Hero UI `Chip`, and SHALL NOT render the Compact button

#### Scenario: Context usage includes active prompt and tool scaffolding
- **WHEN** the dashboard displays context usage for an active session
- **THEN** the displayed estimate SHALL account for the active system prompt content, retained replay history, and active tool definitions returned by the agent-orchestrator

#### Scenario: Context usage respects replay limits
- **WHEN** replay-window settings exclude older history from the next request
- **THEN** the dashboard SHALL reflect the bounded estimate returned by the agent-orchestrator instead of implying that all prior messages still count equally
