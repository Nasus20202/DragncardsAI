## 1. Correct the tool description in game-service

- [x] 1.1 Rewrite the `mulligan_draw_hand` endpoint `summary` in
      `game_action_helpers.py` to state it draws up to hand size, discards
      nothing, and is a no-op on a full hand, keeping the `draw_card`
      preference note.
- [x] 1.2 Correct the `MulliganDrawHandAction` docstring and its `player_n`
      field description in `logic/actions.py`.
- [x] 1.3 Fix the translation comment claiming the action "draws a new hand if
      roundNumber is 0" — only the `LOG` line is round-0 conditional.

## 2. Drop the contradiction framing from the play skill

- [x] 2.1 Rewrite fact 9 in `skills/marvel-champions-play/SKILL.md` to state the
      behaviour without referring to a misleading tool summary.
- [x] 2.2 Rewrite the `mulligan_draw_hand` entry in
      `skills/marvel-champions-play/resources/tool-reference.md` the same way.

## 3. Specs and verification

- [x] 3.1 Update the `mulligan_draw_hand` scenario in
      `openspec/specs/game-service/spec.md` and add a scenario requiring action
      summaries to describe only effects the action performs.
- [x] 3.2 `./scripts/lint.sh --fix` and `./scripts/test.sh unit` pass.
