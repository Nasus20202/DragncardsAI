# dra-52: Hero cards of non-first players are invisible in the DragnCards UI

## Why

DRA-52, verbatim: "Sometimes Hero cards are visible only for the first player. The
DragnCards UI shows only the first player's hero cards, other players' cards are
visible via the mcp, but not in the UI. All cards should be able to be viewed in the
UI. Apparently the player's seat must not be empty for the cards to be visible.
Sometimes it works. Please verify and close if needed."

The reproduction is deterministic and is not a seat-occupancy problem. DragnCards
renders only the groups that have a region in the room's *active layout*. A fresh
Marvel Champions room is laid out with `standard1Player`, whose regions cover only
`player1`'s groups — `player2Engaged`, `player2Play1`, `player2Play2` and the rest of
the second seat's groups exist in the game state but have **no region** to render
into. Loading a hero deck for `player2` while the layout is still `standard1Player`
puts that hero's identity and deck into groups the UI cannot display: the cards are
present in the game state (so `get_game_state` / MCP shows them) but never appear on
the table. Setting the player count afterwards — which switches the layout to
`standard2Player` — makes the cards appear. That is the "sometimes it works": it
works exactly when the player count/layout was set before the second deck was loaded,
and the seat-emptiness observation is a correlation, not a cause (an unclaimed seat
2 with a correct layout shows the hero fine).

The bug report points at the DragnCards UI, which is vendored upstream
(`external/dragncards`). Investigation shows the UI behaviour is intentional upstream
design — the 2D engine renders groups only when their `groupId` has a region in the
layout, and the newer dnc3d adapter codifies exactly that rule in
`engine-dnc3d/adapters/cards.js` ("Skip cards in groups with no layout region"). The
defect is in the *setup order* of an automated game: the human flow always sets the
player count (which switches the layout) before loading decks, while an agent can
load a second seat's deck first. That ordering lives in the game-service's domain.

## What Changes

The game-service's `load_prebuilt_deck` gains a guard that replicates the human
setup order. Before loading a deck for seat `playerN` (`N > 1`), the service reads
the room's current `numPlayers`; if the seat is not covered by the current player
count, it first raises the count — and with it the layout, using the plugin's own
`playerCountMenu` mapping (`standard2Player`, `standard3Player`, …) — and only then
loads the deck. A load for `player1`, or for a seat the current count already covers,
behaves exactly as before.

The guard lives in `SessionManager.load_prebuilt_deck` — the single choke point
behind both `POST /games/{id}/load-prebuilt-deck` and the derived MCP tool — so every
caller is covered, and it is derived from the plugin's published player-count/layout
menu rather than hardcoded to Marvel Champions.

### Modified Capabilities

- `game-service` — loading a prebuilt deck for a seat beyond the room's current
  player count first raises the count and switches the layout, so the deck's cards
  land in groups the UI can display. The normal setup order (count first, then
  decks) is unchanged.

### Impact

- **game-service** —
  `services/game-service/src/game_service/logic/session_manager.py` (the
  `_ensure_seat_has_layout` guard and the `_seat_number` /
  `_layout_id_for_player_count` helpers); four new unit tests in
  `services/game-service/tests/unit/test_load_prebuilt_deck_service.py`.
- **external/dragncards** — none. The UI behaviour (groups without a layout region
  are not rendered) is deliberate upstream design and is left untouched; the
  trigger, not the renderer, is what this change fixes.
- **external/dragncards-mc-plugin** — none. The layout menu is read as-is.
- **agent-orchestrator, history-service, eval-service, dashboard** — none.
- **Documentation** — the game-service spec gains the new requirement; no README
  change is needed (no port, service set, or command changed).

## Non-goals

- **No change to the vendored DragnCards renderer.** Rendering cards of groups the
  active layout does not place would be an upstream product decision (the 3D
  adapter explicitly skips them), and editing vendored code is discouraged.
- **No seat claiming.** The game log's seat-alias completeness is already handled by
  `claim_seats` on the room's player-count route; the visibility bug reproduces with
  a claimed or unclaimed seat alike.
- **No error-on-wrong-order.** Failing the load would surface a confusing error to
  an agent; replicating the human order (bump count, then load) is what the ticket
  asks for ("All cards should be able to be viewed in the UI").
