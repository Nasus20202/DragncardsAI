# Verification and recovery

## The action result contract

Every mutating tool returns:

```json
{ "session_id": "...", "success": true, "error": null }
```

`success` is hard-coded `true` and tells you nothing. **The only failure signal is a
non-null `error`.** The service scans the DragnCards game log after each action for
messages containing `ABORT:` or `Error in Marvel Champions triggered by [...]` and puts the
first one it finds into `error`. The field is reset before each action, so it never
reports a stale failure.

**Read `error` after every mutating call.** If it is non-null:

1. Assume the action did **not** take effect.
2. Do not retry blindly — re-read state with `get_game_state` and confirm what actually
   happened. Some errors fire partway through a multi-step action list.
3. Fix or report. Do not stack further actions on an unverified board.

Example of a real failure:

```
"error": "Error in Marvel Champions triggered by [player1/player1]: Group not found:
 cardByIdsurveillanceteam_-h9iqbfjdeckGroupId Trace: [\"Shuffle card ... into its deck\", \"index 1\"]"
```

## Verification rhythm

You do not need to re-read state after every single call — that burns context. Read after
a **group** of related calls:

- After paying a cost and playing a card → confirm the card is in the play group and the
  right number of cards left your hand.
- After an attack → confirm `tokens.damage` on the target moved by the amount you intended.
- After a thwart → confirm `tokens.threat` moved and did not go negative.
- After flipping → confirm `currentSide` and the new `handSize`.
- At the end of your turn, always → one final read before you report.

Compare against what you expected. If it does not match, stop and diagnose before acting
again.

## `prev_step` is not undo

`prev_step` emits `["PREV_STEP"]`. It moves the shared step marker backwards along
`0.0 → 1.1 → 1.2 → 2.1 → 2.2 → 2.3 → 2.4 → 2.5 → 0.1` and does **nothing else**. Card
moves, token changes, exhaustion, and flips all persist. It is also a table-wide action
you are not allowed to take.

There is no undo. Correct mistakes with inverse actions.

## Inverse actions

| Mistake | Fix |
| --- | --- |
| Moved a card to the wrong group | `move_card` it back to the group it came from. Note the side flips back too. |
| Exhausted the wrong card | `ready_card(<that card>)` |
| Readied a card that should be exhausted | `exhaust_card(<that card>)` |
| Added too many / too few tokens | `modify_tokens` with the difference (negative to remove) |
| Wiped tokens with `zero_tokens` by accident | Re-apply each token with `modify_tokens`. You need the pre-wipe state — this is why you read before you act. |
| Flipped an identity the wrong way | `flip_card` again to cycle back, or `set_card_property(<id>, "currentSide", "A"\|"B")` to force it |
| Paid a cost twice | `move_card` the over-paid cards from `playerNDiscard` back to `playerNHand` |

Order matters when reversing a sequence: undo in the reverse order you did it, so
intermediate states stay coherent.

## Things you cannot fix yourself

- **Drew a card you should not have.** You can `move_card` it from `playerNHand` back to
  `playerNDeck` (it turns facedown on top), but the original card order is gone. Say so.
- **Anything requiring a shuffle.** There is no player-facing shuffle tool and
  `shuffle_into_deck` is broken. Report it.
- **A card that left the game or was mangled by an aborted plugin action list.** Report it
  and stop; do not improvise with `raw_action`.

When you cannot fix something, say exactly what happened, what the board looks like now,
and what the correct board would be. A coordinator or human can repair it with HTTP-only
tools you do not have.

## Common failure modes and their causes

| Symptom | Likely cause |
| --- | --- |
| `Group not found: cardById<id><field>` | A tool built a malformed DragnLang path. Known for `shuffle_into_deck`. |
| Action returns `error: null` but state did not change | You targeted a `HIDDEN` entry's inherited `instanceId`, which points at the wrong card — or at a card the action is a no-op for. |
| Card vanished from the zone listing after a move | You moved it onto another card's stack (`dest_card_index` > 0). It is now an attachment; check the host's `stackSize`. |
| Card came back facedown | You moved it into a `*Deck` group; those set `currentSide: "B"` on entry. |
| Token count is negative | You subtracted more than was there. Nothing clamps. Add the difference back. |
| `handSize` changed without you drawing | You flipped your identity; hero and alter-ego sides have different hand sizes. |
| Hand did not refill after `mulligan_draw_hand` | Your hand was already at or above `handSize`. That tool only draws *up to* the limit and never discards. |
| Everything on the table readied and every player redrew | Someone called `player_end_phase`. If it was you, report it — it advanced the phase for the whole table. |

## Reporting

End every turn with a short report containing:

1. What you did, in order.
2. The resulting board numbers: your remaining HP, villain remaining HP, main scheme threat,
   what is still in `playerNEngaged`, cards left in hand.
3. Anything you deliberately left ready, and why.
4. Any `error` you hit and whether you recovered from it.

Then stop. Do not advance the step, do not refill your hand, do not act for anyone else.
