# Tasks

Ordered so each section is independently shippable and a partial run leaves a green
test suite at the end of every task.

## 1. Confirm where the bug lives

- [x] 1.1 Reproduce: create a Marvel Champions room, load a hero deck for `player2`
      **before** setting the player count. Confirm the hero card is present in the
      raw game state (`get_game_state` shows it) but absent from the rendered
      DragnCards table (Playwright DOM dump shows no image for it), while `player1`'s
      hero renders.
- [x] 1.2 Confirm the trigger is the layout, not seat occupancy: with seat 2
      unclaimed but the layout already `standard2Player`, both hero cards render.
- [x] 1.3 Confirm the UI behaviour is intentional upstream: the 2D engine renders a
      group only when its `groupId` has a region in the active layout, and the
      upstream dnc3d adapter codifies the same rule ("Skip cards in groups with no
      layout region"). No vendored renderer change is warranted.

## 2. Fix the setup ordering in game-service

- [x] 2.1 Add `_ensure_seat_has_layout` to `SessionManager.load_prebuilt_deck`
      (`services/game-service/src/game_service/logic/session_manager.py`): before
      loading a deck for seat `playerN` (`N > 1`), read the room's `numPlayers` and,
      when the seat is not covered, call `session.set_player_count` with the plugin's
      layout for that count (derived from `playerCountMenu` via
      `get_plugin_action_catalog`).
- [x] 2.2 Seat 1 and already-covered seats must be untouched: a `player1` load with
      count 1, and a `player2` load with count 2, must not call `set_player_count`.
- [x] 2.3 Add `_seat_number` and `_layout_id_for_player_count` module helpers.

## 3. Tests

- [x] 3.1 Unit tests in
      `services/game-service/tests/unit/test_load_prebuilt_deck_service.py`:
      uncovered seat bumps count+layout; covered seat does not; seat 3 bumps from
      count 1; a missing `numPlayers` still bumps for seat 2.
- [x] 3.2 Verify end-to-end against a running stack: load `player2`'s deck first and
      confirm the room state reports `numPlayers: 2` / `standard2Player` and the
      second hero card renders in the UI.

## 4. Validation

- [x] 4.1 `./scripts/lint.sh` clean.
- [x] 4.2 `./scripts/test.sh unit` green (game-service 482 tests including the four
      new ones).
- [x] 4.3 `openspec validate --all` continues to report exactly one pre-existing
      failure (`spec/typed-game-actions`); this change does not add a second.
- [x] 4.4 Archive the change with `openspec archive dra-52-hero-visibility --yes` and
      confirm `openspec/changes/archive/` contains the result.
