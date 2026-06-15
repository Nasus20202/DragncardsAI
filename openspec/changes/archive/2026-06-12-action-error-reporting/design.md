## Context

The game-service already has error handling for action execution. When a DragnCards action fails, errors appear in `game.messages` with format "Error in Marvel Champions triggered by ...". The `execute_action` method now extracts these errors into `_action_error` for the response.

## Goals / Non-Goals

**Goals:**
- Return error field when DragnCards action fails (errors in `game.messages`)
- Verify action helper endpoints return error field

**Non-Goals:**
- No changes to alert-based error capture (that remains unchanged)

## Decisions

### Decision: Extract errors from game.messages
- **Alternative**: Only use `send_alert` events - rejected because DragnCards puts many action errors in messages array instead
- **Rationale**: Check `game.messages` for "Error in Marvel Champions triggered" pattern mirrors the pattern in `load_prebuilt_deck`

## Risks / Trade-offs

- **Risk**: DragnCards may not log all action failures
- **Mitigation**: Check both alert-based and message-based errors for comprehensive coverage