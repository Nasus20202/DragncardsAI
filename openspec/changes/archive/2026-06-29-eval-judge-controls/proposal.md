## Why

The on-demand evaluation feature works, but the judge is a black box: the model, reasoning, prompt/rubric, and rules skills are fixed server-side env config, evaluations give no live feedback (only 2s status polling) and cannot be cancelled, the history/eval game picker only lists agent-orchestrator play-sessions (so recorded games — including finished ones — are not selectable), and there is no way to remove a game's history. Users want the evaluation experience to have the same configurability as the Play-game flow, with real-time progress, cancellation, a history-driven game picker, and history cleanup.

## What Changes

- **eval-service** SHALL accept a per-evaluation `judge` configuration (provider, model, reasoning effort, custom prompt/rubric, and selected rules skills) that overrides the server defaults, honoring it for that evaluation and recording the effective model/provider on the verdict.
- **eval-service** SHALL stream evaluation progress over Server-Sent Events (per-target status transitions and incremental judge output) and SHALL support cancelling an in-flight evaluation request, introducing a terminal `cancelled` state.
- **history-service** SHALL expose a list of games that have recorded history and SHALL support deleting all history for a game.
- **dashboard** SHALL source the history/eval game picker from games-with-history, add a delete-history control, add a Play-parity judge configuration panel to the Evaluate control, and render live SSE status with a Cancel button.

## Capabilities

### Modified Capabilities

- `agent-move-evaluation`: per-evaluation judge configuration (provider/model/reasoning/prompt/skills), SSE streaming of status + judge output, and cancellation with a `cancelled` terminal state.
- `history-event-store`: list games-with-history and delete a game's history.
- `game-history-ui`: history-driven game picker, delete-history control, Play-parity judge config panel, and live SSE status with cancel.

## Impact

- eval-service: extended request schema + persisted judge config, SSE stream endpoint, cancel endpoint, streaming/cancellable Bifrost client, `SKILL_ROOTS` setting and skill-content loading, `cancelled` status.
- history-service: `GET /games` and `DELETE /games/{game_id}` plus repository support.
- dashboard: new history-games client + picker, delete control, judge config panel reusing the Play provider/skill sources, EventSource-based live status, and cancel.
- No change to the game-playing agent or the upstream DragnCards backend.
