# Play recipes

Ordered tool-call sequences for everything you do on a turn. `N` is your player number —
substitute the concrete group id (`player1Play2`, not `playerNPlay2`).

Every `instance_id` comes from the current `get_game_state` output requested with your
assigned `player_n`. Never construct one.
After every sequence, check the `error` field on each response.

---

## Paying a cost

There is no cost enforcement. Paying is a thing **you** do, and it is always the same:

> For each resource the card costs, move one card from `playerNHand` to `playerNDiscard`.

```
move_card(instance_id=<resource card 1>, dest_group_id="playerNDiscard", dest_stack_index=-1, player_n="playerN")
move_card(instance_id=<resource card 2>, dest_group_id="playerNDiscard", dest_stack_index=-1, player_n="playerN")
...
```

Rules that you must apply yourself because nothing checks them:

- A card discarded for resources generates the icon in its catalog `resource` field
  (`{m}` mental, `{p}` physical, `{e}` energy, `{w}` wild). Most player cards generate one.
- Dedicated **resource-type** cards (`type_code: "resource"`) may generate more or have
  a printed effect — read their `rules`.
- Aspect cards must be paid with matching or wild icons where the card demands it.
- Your alter-ego identity may have a once-per-round resource ability (e.g. Peter Parker's
  "Scientist — Resource: Generate a `{m}` resource"). Using it costs nothing to model:
  just pay one fewer card and note it in your report.

Count carefully before you start moving cards — a half-paid cost is hard to unwind.

---

## Playing an ally, upgrade, or support

```
# 1. pay
move_card(<resource card>, "playerNDiscard", dest_stack_index=-1, player_n="playerN")   # x cost
# 2. put it into play
move_card(<the card>, "playerNPlay2", dest_stack_index=-1, player_n="playerN")
```

The card enters faceup and ready. Then apply its entering-play effect by hand:

- Ally with a "Response: after X enters play, remove 1 threat" → `modify_tokens` on the scheme.
- Support with "Uses (3 counters)" → `modify_tokens(<the card>, "generic", 3)`.
- Upgrade that attaches to a card → move it onto the host stack instead:
  `move_card(<upgrade>, "<host's group>", dest_stack_index=<host's stack index>, dest_card_index=1)`.
  It disappears from the zone listing and shows up as an increased `stackSize` on the host.

---

## Playing an event

Events resolve and go to the discard. `playerNEvent` is the staging row while it resolves.

```
move_card(<resource card>, "playerNDiscard", dest_stack_index=-1, player_n="playerN")   # x cost
move_card(<the event>, "playerNEvent", dest_stack_index=-1, player_n="playerN")
# ... apply the event's effect with modify_tokens / draw_card / move_card ...
move_card(<the event>, "playerNDiscard", dest_stack_index=-1, player_n="playerN")
```

If the event is a simple one-shot you may skip the `playerNEvent` hop and move it straight
to the discard after applying the effect. Use the staging row when the event's resolution
involves several steps and you want the board to show what is happening.

---

## Basic attack (hero form)

Hero form only. Your hero must be ready.

```
# 1. commit
exhaust_card(<your identity card>)
# 2. deal damage equal to your hero side's ATK
modify_tokens(<target enemy card>, "damage", <your ATK>)
```

Your ATK is the `attack` attribute of your identity's `type_code: "hero"` catalog record.

Targets: the card in `sharedVillain`, or a minion in your `playerNEngaged`. You cannot
attack the villain while a minion is engaged with you unless an effect says otherwise.

**Defeat check.** After damaging:

- Villain: remaining = `villainHitPoints` − `tokens.damage`. At ≤ 0, the stage is defeated
  — stop and report; stage advancement is the coordinator's job.
- Minion: remaining = catalog `health` − `tokens.damage`. At ≤ 0, move it to the encounter
  discard: `move_card(<minion>, "sharedEncounterDiscard", dest_stack_index=-1)`.

**Tough.** If the target has `tokens.tough >= 1`, the attack removes the tough status
instead of dealing damage: `modify_tokens(<target>, "tough", -1)` and deal no damage.

---

## Basic thwart (hero form)

```
exhaust_card(<your identity card>)
modify_tokens(<the scheme card>, "threat", -<your THW>)
```

Your THW is the `thwart` attribute of your hero-side catalog record.

Targets: `sharedMainScheme[0]`, or a side scheme in `playerNEngaged`.

Clamp it yourself: if the scheme has 2 threat and you thwart for 3, apply `-2`, not `-3`.
Negative threat is not a legal board state and nothing will stop you creating one.

When a side scheme reaches 0 threat it is defeated:
`move_card(<side scheme>, "sharedEncounterDiscard", dest_stack_index=-1)`. If it has a
`Victory X` line in its rules, send it to `sharedVictoryDisplay` instead.

---

## Defend (hero form, during the villain phase)

You will be asked to defend by whoever is running the villain phase.

```
exhaust_card(<your identity card>)
# damage taken = attack value - your DEF (minimum 0)
modify_tokens(<your identity card>, "damage", <reduced damage>)
```

Your DEF is the `defense` attribute of your hero-side catalog record. Compute the reduced
amount yourself: `max(0, attack_value + boost_icons - defense)`.

An ally can defend instead — exhaust the ally and put the damage on the ally:

```
exhaust_card(<the ally>)
modify_tokens(<the ally>, "damage", <reduced damage>)
```

If the ally's `tokens.damage` reaches its catalog `health`, it is defeated:
`move_card(<ally>, "playerNDiscard", dest_stack_index=-1, player_n="playerN")`.

---

## Taking damage undefended

```
modify_tokens(<your identity card>, "damage", <full attack value>)
```

Then check: remaining = `players.<you>.hitPoints` − `tokens.damage`. At ≤ 0 you are
defeated — report it immediately and stop acting.

**Tough on you.** If your identity has `tokens.tough >= 1`, cancel the damage entirely and
`modify_tokens(<your identity card>, "tough", -1)` instead.

---

## Changing form

```
flip_card(<your identity card>)
```

Nothing else changes: you keep your hand, your tokens, and your ready/exhausted state. The
`handSize` reported in `players.<you>` updates to the new side's value.

Side `A` is the hero, side `B` is the alter-ego. Read `currentSide` before flipping so you
know which way you are going — `flip_card` cycles, it does not target a side. If you need
a specific side, use `set_card_property(<identity>, "currentSide", "A")`.

Marvel Champions allows one form change per turn; the harness does not enforce it.

---

## Recovering (alter-ego form)

```
exhaust_card(<your identity card>)
modify_tokens(<your identity card>, "damage", -<your REC>)
```

Your REC is the `recover` attribute of your identity's `type_code: "alter_ego"` catalog
record. Clamp it: never take `tokens.damage` below 0. If you are healing to full, use
`modify_tokens(<identity>, "damage", -<current damage>)` rather than guessing.

Do **not** use `zero_tokens` for a recover — it would also wipe statuses and threat.

---

## Using a card ability that requires exhausting

Most support and ally abilities read "Action: Exhaust X → do Y", and many spend a counter.

```
exhaust_card(<the card>)
modify_tokens(<the card>, "generic", -1)          # only if the ability spends a counter
# ... apply Y ...
modify_tokens(<scheme>, "threat", -1)             # example: "remove 1 threat from a scheme"
```

Counters printed as "Uses (N ... counters)" are modelled with the `generic` token. Set them
when the card enters play and decrement them as they are spent.

---

## Ally attacks and thwarts

Allies act like a second hero, and most take consequential damage when they attack.

```
exhaust_card(<the ally>)
modify_tokens(<target>, "damage", <ally's ATK>)
modify_tokens(<the ally>, "damage", 1)            # consequential damage, if the ally has it
```

Thwarting with an ally is the same shape with the ally's `thwart` value and a negative
`threat` change. Check the ally's `rules` — the consequential damage is printed on the card
as a `{d}` icon next to the value (visible as `"1 {d}"` in the catalog `attack` field).

---

## Drawing from a card effect

```
draw_card(player_n="playerN", count=<N>)
```

Only when a card says "draw N cards". Do **not** use it to refill to hand size at end of
turn — that is the coordinator's `player_end_phase`, which draws every player up at once.

---

## Discarding down to hand size

The harness never enforces the hand limit and `mulligan_draw_hand` will not do it for you.
If the coordinator asks you to discard down:

```
move_card(<card to discard>, "playerNDiscard", dest_stack_index=-1, player_n="playerN")   # repeat
```

Discard until `len(zones["playerNHand"])` equals `players.<you>.handSize`.

---

## Returning a card to your deck

If the effect says **shuffle it into your deck**:

```
shuffle_into_deck(<the card>, player_n="playerN")
```

It finds the card's own deck, moves it there facedown, and shuffles that deck. You do not
pass a destination group — but you do pass `player_n`, or deck-insertion automation fails
with `Variable $PLAYER_N is undefined`.

If the effect says **put it on top of your deck** — no shuffle — use:

```
move_card(<the card>, "playerNDeck", dest_stack_index=0, player_n="playerN")
```

Either way the card is turned facedown automatically. Pick the one the card text asks for;
they are not interchangeable.
