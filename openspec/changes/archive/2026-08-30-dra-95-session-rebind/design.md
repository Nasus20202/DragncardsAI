## Context

The existing binding guard intentionally prevents a session that has captured one game id from reading or mutating another game. Game-service `create_game` is different from an attach or state call: it creates a new game and is the explicit operation used by reset-and-replay. The current capture path nevertheless treats every source-tool result as immutable once a binding exists. Persistent seat sessions are linked from the orchestrator's player configuration and independently retain the old game id, so changing only the parent would leave the next seat prompt refused.

## Goals / Non-Goals

**Goals:**

- Make successful reset-and-replay through `create_game` usable with an existing orchestrated session.
- Keep the authorization boundary for existing games unchanged.
- Retire old seat sessions without deleting their durable records.
- Preserve configured seat provider, model, persona, skill, and display-name settings.

**Non-Goals:**

- Allow arbitrary metadata writes or ordinary game-service calls to rebind a session.
- Delete or rewrite prior transcripts.
- Change game-service protocol behavior, WebSocket handling, or provider failure handling.

## Decisions

1. **Use successful `create_game` as the explicit rebind signal.**
   - The capture path will accept a different result id only for a non-error `create_game` response.
   - `attach_game`, `lookup_session_by_slug`, reads, actions, and turn operations remain immutable and continue through the existing guard.
   - Alternative rejected: allow every lifecycle source to rebind. That would permit attaching an existing foreign game and would weaken the authorization boundary.

2. **Rotate seats at the binding transition.**
   - When the parent binding changes, atomically clear all linked seat-session ids in the player-config store, then terminate the returned old child sessions.
   - The next `prompt_player_agent` call follows the existing missing-link path and creates a fresh child with the current parent game id and preserved seat configuration.
   - Alternative rejected: modify `prompt_player_agent` to silently replace a mismatched child. That spreads replay detection across the dispatch path and risks reusing a stale child after a non-creation binding change.

3. **Keep retired child rows terminated.**
   - Termination preserves transcripts and gives operators an auditable record of the prior game while preventing future reuse.
   - Alternative rejected: hard-delete children. Deletion would remove the seat's prior reasoning and tool history and would make post-failure diagnosis impossible.

4. **Perform rotation only after a successful, identified creation result.**
   - Errors, missing ids, and ambiguous result/argument ids do not change metadata or seat links.
   - Alternative rejected: reset on the request before the response. A failed provider/game-service call would strand the current session and make retry recovery worse.

## Risks / Trade-offs

- The orchestrator transcript remains multi-game history. The durable binding and newly created child sessions prevent cross-game tool access, but the model still receives prior messages according to its configured context window; reset prompts must clearly establish the replacement game.
- A process crash between clearing seat links and terminating old children can leave terminated cleanup pending, but no new prompt can reuse a cleared link. Retrying termination is safe because it is idempotent.
- The implementation depends only on the existing game-service lifecycle response shape and does not alter DragnCards or marvel-lcg WebSocket behavior. If an upstream adapter returns an ambiguous creation result, the conservative path leaves the old binding intact.
