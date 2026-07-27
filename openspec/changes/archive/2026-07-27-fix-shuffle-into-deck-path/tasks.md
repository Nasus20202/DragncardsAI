## 1. Fix the emitted DragnLang

- [x] 1.1 In `ShuffleIntoDeckAction` translation, replace the `VAR` argument
      `"/cardById/<id>/deckGroupId"` with the dotted read
      `"$GAME.cardById.<id>.deckGroupId"`.
- [x] 1.2 Leave `MOVE_CARD` and `SHUFFLE_GROUP` unchanged — they were correct
      and only ever received a bad group id.
- [x] 1.3 Comment the translation with why a `/`-prefixed literal is a write
      path and not a read, so the mistake is not reintroduced.

## 1b. Supply player context

- [x] 1b.1 Add an optional, validated `player_n` to `ShuffleIntoDeckAction`,
      mirroring `MoveCardAction.player_n`.
- [x] 1b.2 Return `action.player_n` from the translation instead of `None` so
      `player_ui.playerN` is injected and deck-insertion automation resolves
      `$PLAYER_N`.

## 2. Tests

- [x] 2.1 Update `test_translate_shuffle_into_deck` to the corrected action
      list.
- [x] 2.2 Add a unit test asserting the deck-group expression starts with
      `$GAME.` and contains no `/`, and that the move and shuffle both target
      the resolved `$DECK_GROUP_ID`.
- [x] 2.3 Add unit tests that `player_n` populates `player_ui.playerN` and that
      `player_ui` is omitted when it is unset.
- [x] 2.4 Add an integration regression test that loads a hero deck through the
      manager (so the load is polled to completion), draws a hand, shuffles a
      real card back with `player_n`, and asserts `get_action_error()` is
      `None`, the card is in its `deckGroupId` group, and the deck grew by one.
- [x] 2.5 Keep the existing `test_shuffle_into_deck_action` smoke test.

## 3. Skill documentation

- [x] 3.1 `resources/tool-reference.md` — replace the "**BROKEN**" section with
      the working behaviour, the emitted DragnLang, and the fact that the
      destination is the card's own `deckGroupId`.
- [x] 3.2 `resources/play-recipes.md` — "Returning a card to your deck" now
      routes shuffle effects to `shuffle_into_deck` and top-of-deck effects to
      `move_card`.
- [x] 3.3 `SKILL.md` — harness fact 10 no longer calls the tool broken; it
      states that the tool picks its own destination and cannot be redirected.
- [x] 3.4 `resources/recovery.md` — drop "`shuffle_into_deck` is broken" from
      the unfixable list, and generalise the `Group not found` row to the real
      cause (a `/a/b/c` literal evaluates to a path list).

## 4. Verification

- [x] 4.1 Reproduce the failure live via the `raw` action with the old
      expression; confirm the exact `Group not found:` message.
- [x] 4.2 Run the corrected expression live; confirm `error: null`, the card
      moved from `player1Hand` into `player1Deck`, and the deck order changed.
- [x] 4.3 `./scripts/lint.sh --fix` and `./scripts/test.sh unit` pass.
- [x] 4.4 `./scripts/test.sh integration game-service` passes against the
      running stack.
