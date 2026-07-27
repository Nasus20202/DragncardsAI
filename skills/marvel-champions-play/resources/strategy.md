# Playing well

Marvel Champions is a race: the villain's threat clock versus your damage clock. Every
turn you are deciding which clock to push. All the heuristics below are written in terms
of values you can read or derive from `get_game_state`.

## The two clocks

**Their clock — threat.** Per round the main scheme gains:

```
threat_gain = scheme_acceleration + sharedMainScheme[0].tokens.acceleration
            + sum(acceleration icons on cards in play)
```

You cannot read the scheme's base acceleration from the simplified state, but you can
measure it: note `tokens.threat` at the start of two consecutive rounds and subtract your
own thwarting. In a standard scenario it is typically 1 per player per round, plus any
acceleration tokens the encounter deck has added.

```
rounds_until_loss = (target_threat - current_threat) / threat_gain
```

If you do not know `target_threat` (see `resources/reading-state.md` — it is often not
exposed), ask for it once at the start and cache it.

**Your clock — damage.** Villain remaining HP divided by your realistic damage per round.

```
rounds_until_win = (villainHitPoints - villain_damage) / your_damage_per_round
```

## The core decision

- `rounds_until_loss` clearly larger than `rounds_until_win` → **push damage.** Attack,
  play attack events, develop attack upgrades.
- `rounds_until_loss` at or below `rounds_until_win` → **thwart.** You cannot win a race
  you lose first.
- Both tight → build board. A turn spent playing two allies usually buys more than a turn
  spent doing 3 damage, because allies act every subsequent round.

Concretely: if the main scheme's `tokens.threat` will exceed the target within two rounds
at the current gain rate, thwarting is not optional.

## Side schemes and minions come first

Anything in your `playerNEngaged` is a compounding problem:

- **Side schemes** often carry acceleration or crisis effects and permanently raise
  `threat_gain`. Clearing one this turn is worth more than the same thwart applied to the
  main scheme.
- **Minions** attack you every villain phase and block you from attacking the villain.
  Kill them the turn they appear if you can, unless the villain is one hit from dying.

Check `playerNEngaged` every turn before you plan anything else.

## When to flip to alter-ego

Flip when **all** of:

- Your remaining HP (`hitPoints` − `tokens.damage`) is below roughly half your maximum.
- You can afford to give up a hero-form turn — i.e. the threat clock is not about to run out.
- Your alter-ego `recover` value meaningfully closes the gap. Recovering 2 when you took
  4 last round is treading water.

Flip **immediately** if remaining HP is at or below the villain's `attack` value plus a
couple of boost icons — one bad villain phase defeats you and a defeated hero loses the game.

Do not flip when:

- A minion is engaged with you. Alter-egos cannot defend well and you cannot attack it back.
- You are the only player able to thwart and the scheme is close to target.
- Your alter-ego side has a big draw or resource ability you cannot use profitably this turn.

Alter-ego turns are also the best time to use alter-ego-only cards and to soak up an
encounter you can survive. A hero at full HP that flips down for the ability is usually
making a mistake.

## Resource curve

You have `handSize` cards and every card you spend as a resource is a card you did not
play. A 3-cost card costs you four cards of hand: itself plus three resources.

- Prefer plays that leave you with cards in hand. Two 1-cost allies beat one 3-cost ally
  in most early rounds.
- Cards with `type_code: "resource"` are pure payment — spend them first.
- Cards you will never play in this matchup are resources. Do not hoard a situational
  event for six rounds.
- Look at your discard: it tells you what your deck has already given you and what is left.

Rough shape: rounds 1–2 develop the board with cheap permanents, rounds 3+ convert the
board into damage or thwart every turn while paying for one impactful card.

## Board development

Cards in `playerNPlay2` that exhaust for value are the engine. Each one is a free action
every round for the rest of the game. Ordering:

1. Permanents that generate resources or cards.
2. Allies with useful stats and abilities.
3. Upgrades that raise your ATK / THW / DEF.
4. One-shot events, played when they swing a specific turn.

An ally is worth roughly its `health` in blocked damage plus its stats every round. Do not
throw allies away chump-blocking early unless the alternative is your own defeat.

## Efficiency checklist before you stop

Run this before you report your turn done:

- Is my identity exhausted? If not, is there a reason (holding it to defend)?
- Is every ally and support with a usable ability either exhausted or deliberately held?
- Did I clear everything in `playerNEngaged` that I could?
- Did I leave threat on a side scheme I could have finished?
- Do I have a card in hand I can still afford?
- Did I apply every "Response:" and "Action:" I triggered?

Wasted readiness is the single most common way an agent plays badly here — nothing in the
harness reminds you that a card is still available.

## Holding back deliberately

Two legitimate reasons to end a turn with a ready card:

1. **Defense.** Keeping your hero ready lets you defend during the villain phase, which is
   usually worth more than a basic attack if the incoming attack exceeds your remaining HP.
2. **Interrupts and responses.** An ally or upgrade whose ability triggers during the
   villain phase must be ready then.

Say so in your report so the coordinator knows the readiness is intentional.
