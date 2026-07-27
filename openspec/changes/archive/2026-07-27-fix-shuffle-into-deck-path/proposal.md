# `shuffle_into_deck` emits a malformed DragnLang path and never moves the card

## Why

`shuffle_into_deck` has never worked. Every call fails with, verbatim:

```
Error in Marvel Champions triggered by [player1/dev_user]: Group not found:
cardByIddefensemechanism_aybphtwodeckGroupId Trace: ["repro old", "index 1"]
```

The card stays where it was.

The action translated to:

```python
["VAR", "$DECK_GROUP_ID", f"/cardById/{instance_id}/deckGroupId"]
["MOVE_CARD", instance_id, "$DECK_GROUP_ID", 0]
["SHUFFLE_GROUP", "$DECK_GROUP_ID"]
```

The `VAR` argument is the bug. In DragnLang a string that starts with `/` is a
**write-path literal**, not a getter. `Evaluate.evaluate/3` turns it into the
path *list* it denotes:

```elixir
is_binary(code) and String.starts_with?(code, "/") ->
  split = String.split(code, "/")
  path = ["LIST"] ++ Enum.slice(split, 1, Enum.count(split))
  List.flatten(evaluate(game, path, trace))
```

So `$DECK_GROUP_ID` was bound to `["cardById", "<id>", "deckGroupId"]` — the
path — rather than to the group id stored there. `MOVE_CARD` passed that list
to `GameUI.move_card/6`, which failed its `dest_group_id not in
Map.keys(game["groupById"])` check and raised `"Group not found:
#{dest_group_id}"`. Elixir interpolates a list of binaries as concatenated
iodata, which is why the three path segments appeared glued together as
`cardById<id>deckGroupId` with the separators gone. The "missing separator"
appearance was a red herring: the string was never a group id at all.

Reads must use dotted `$GAME.` access, which resolves via `OBJ_GET_BY_PATH`.
That is the idiom the Marvel Champions plugin itself uses in its own
`shuffleIntoDeck` action list (`["VAR", "$GROUP_ID",
"$ACTIVE_CARD.deckGroupId"]`), and the one the service's own `flip_card`
already uses to read `$GAME.cardById.<id>.currentSide`. `shuffle_into_deck` was
the only action that tried to *read* through a `/`-prefixed literal.

The existing tests could not catch this. The unit test asserted the emitted
action list equalled the buggy literal, and the integration test called the
action against a nonexistent card id and only asserted that some state came
back — never that the card moved, and never that `error` was null.

### A second defect behind the first

Fixing the path exposed a second failure that the group-not-found error had
been masking. With a usable group id, the move reached the Marvel Champions
deck-insertion automation, which evaluates `["EQUAL", "$CARD.deckGroupId",
"{{$PLAYER_N}}Deck"]`, and the action failed with:

```
Failed to insert new stack at index 0 in group player1Deck. Error: :
Variable $PLAYER_N is undefined.
```

`ShuffleIntoDeckAction` returned `None` for player context, so
`translate_action` never set `player_ui.playerN` on the request. Every other
player-scoped action already supplies it — `MoveCardAction` even infers it from
a `playerN`-prefixed destination group. `shuffle_into_deck` had no way to say
who was shuffling, so it could not have worked even with a correct path.

## What Changes

- **game-service** — `ShuffleIntoDeckAction` reads the deck group with
  `$GAME.cardById.<id>.deckGroupId` instead of `/cardById/<id>/deckGroupId`.
  The move and shuffle steps are unchanged; they were always correct and simply
  never received a usable group id.
- **game-service** — `ShuffleIntoDeckAction` gains an optional `player_n`,
  validated and defaulted to `None` exactly like `MoveCardAction.player_n`, and
  the translation passes it through so `player_ui.playerN` is injected. It is
  optional for backward compatibility and because shared-deck cards do not need
  it, but it is required in practice for any card returning to a `playerNDeck`.
- **Unit tests** — the expected action list is updated, and a second test
  pins the property that actually matters: the deck-group expression is a
  dotted `$GAME.` read and contains no `/`, so the buggy form cannot be
  reintroduced by an equality assertion alone.
- **Integration tests** — a real end-to-end regression test loads a hero deck,
  draws a hand, shuffles a genuine card back, and asserts `error` is null, that
  the card is now in its `deckGroupId` group, and that the deck grew by one.
  The old smoke test is kept as-is.
- **`skills/marvel-champions-play`** — the skill documented the tool as broken
  and told agents to use a `move_card` workaround. `SKILL.md`,
  `resources/tool-reference.md`, `resources/play-recipes.md`, and
  `resources/recovery.md` now describe the working tool and draw the real
  distinction: `shuffle_into_deck` for "shuffle it into your deck",
  `move_card` for "put it on top of your deck".

## Non-goals

- Adding a general "shuffle this group" tool. `shuffle_into_deck` still only
  shuffles the deck the card itself belongs to.
- Letting the caller choose the destination group. The destination stays the
  card's own `deckGroupId`; a card without one still fails rather than guessing.
- Auditing other actions for the same mistake. `shuffle_into_deck` was the only
  action reading through a `/`-prefixed literal; every other `/` path in the
  module is a `SET` / `INCREASE_VAL` write target, where the path list is
  exactly what is wanted.
- Inferring `player_n` from game state. `translate_action` is a pure, state-free
  function, and unlike `move_card` there is no destination group in the request
  to infer from — the destination lives on the card. Making the translation
  state-aware is a larger change than this fix warrants.

## Impact

- Affected specs: `game-service` (new requirement: shuffle-into-deck moves the
  card into its own deck and shuffles it), `marvel-champions-play-skill`
  (the "known-broken tool" scenario is replaced).
- Affected code:
  `services/game-service/src/game_service/logic/actions.py`,
  `services/game-service/tests/unit/test_action_translation.py`,
  `services/game-service/tests/integration/test_actions.py`,
  `skills/marvel-champions-play/`.
- No API, schema, or migration changes. The tool's request and response shapes
  are untouched — it simply now does what it always claimed to do.

## Verification

Verified live against the running stack. Using the `raw` action escape hatch on
a throwaway Spider-Man (Miles Morales) session, the old expression reproduced
`Group not found: cardByIddefensemechanism_aybphtwodeckGroupId` exactly, and
the new expression returned `error: null`, moved the card from `player1Hand`
(5 → 4 stacks) into `player1Deck` (35 → 36 stacks), and changed the deck's
stack order — confirming the shuffle also ran.

The `$PLAYER_N` defect was found by the new integration test rather than by
inspection: with the path fixed and no player context, the test failed with the
insertion error above, and passes once `player_n` is supplied.
