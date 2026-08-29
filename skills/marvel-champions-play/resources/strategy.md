# Playing well

Marvel Champions is a race: the villain's threat clock versus your damage clock. Every
turn you decide which clock to push, but you must account for every active scheme effect
before choosing a line. The procedure below uses only the normalized state and values
that are explicitly supplied or looked up. It never fills an unavailable value with a
standard-scenario guess.

## Evidence-first planning pass

Call `get_game_state(session_id, player_n=<your assigned seat>)` at the start of the turn
and after every meaningful board change. Confirm `phase == "player"` before planning a
player turn. Read the active main scheme as `zones.sharedMainScheme[0]` and inspect every
card in `zones.sharedSideSchemes`; do not collapse side schemes into one generic threat
total.

For the main scheme, record:

- `current_threat`: `sharedMainScheme[0].tokens.threat`. A missing token key is zero
  because normalized tokens are sparse. A missing active main-scheme card is not zero; it
  is an unavailable board fact and must be reported.
- `target_threat`: the explicit `tokens.target_threat` value when present, or a value
  returned by an allowed card lookup or supplied by the coordinator/human. Never infer a
  target from a familiar scenario, card name, or the current phase.
- `base_placement`: the explicit amount that will be placed during the next villain
  phase for this scenario and player count. Use a value in state, an explicit
  coordinator/human statement, or an explicit card/rules lookup. Do not silently use
  one threat per player.
- `acceleration`: every explicit acceleration value that applies to the main scheme,
  including `tokens.acceleration` on the main scheme and on active side schemes when
  the state says it contributes to main-scheme placement.
- `alter_ego_scheme`: each known villain or minion scheme contribution for an activation
  against a player currently in alter-ego form. Look up the visible enemy's printed
  `scheme` value when the state does not carry it. A hidden boost card or unreported
  modifier is not a number to add.
The known values in this `alter_ego_scheme` term are the **known alter-ego schemes** in
the minimum: enemy scheme contributions against players currently in alter-ego form.
Unknown boosts remain excluded rather than guessed.

If a required term is absent or non-numeric, name that term, ask the coordinator or
human (or perform the permitted explicit lookup), and stop short of claiming an exact
clock or safety result. A sparse optional token is different: its missing key means
zero, but it never supplies a missing card, target, base placement, or required gain.

## Side schemes: rank the effect, not just the threat

Iterate `zones.sharedSideSchemes` and write one short entry for each named card before
planning an attack or thwart. For each entry, copy its current `tokens.threat` and every
non-zero effect indicator that is actually present:

| Reported indicator | What it means for planning |
| --- | --- |
| `tokens.crisis` | Player cards cannot remove threat from the **main scheme** while the Crisis effect is active. Side-scheme threat remains a legal target; Crisis does not block removing threat from an eligible side scheme. |
| `tokens.hazard` | Additional encounter pressure during the villain phase. Report the indicator; do not turn it into guessed damage, cards, or resources. |
| `tokens.acceleration` | Additional threat placement on the main scheme when the state says this card's acceleration applies. Include the explicit value in the minimum projection. |
| Explicit `tokens.hand` or `tokens.resource` denial | Hand or resource denial is active only when the corresponding normalized indicator is present. Report its value or presence without inventing a discarded-card or resource count. |
| `tokens.threat` | Current threat on this side scheme. It is a separate target and is not main-scheme threat. |

Apply these checks in order:

1. If a Crisis indicator is non-zero and the current plan needs player-card removal from
   the main scheme, mark that card as an action blocker and rank clearing/resolving it
   first. Do not spend a player-card thwart on the main scheme while Crisis remains.
2. Rank explicit acceleration by the amount it adds to the next placement. It changes
   the threat clock immediately; never count a side scheme's threat as acceleration.
3. Rank explicit Hazard indicators by their reported encounter pressure, then explicit
   hand/resource denial by its reported value or presence.
4. Use current side-scheme threat and the current available thwart to decide which
   remaining scheme can actually be cleared. A high threat value alone does not grant an
   unreported effect or make an unaffordable line legal.

This is a conditional priority, not a reason to ignore a deterministic clock. If the
minimum next-phase threat reaches the target, threat control outranks villain damage
unless the state explicitly shows that no legal threat-control line exists. If Crisis
blocks that line, say so and clear or resolve the blocker when possible. If an effect is
not represented in the normalized card's tokens (and is not returned by an explicit
permitted lookup), call it unknown; never infer it from the name or remembered text.

## The minimum next-villain-phase threat

Compute the known minimum before choosing between damage and threat control:

```text
minimum_next_main_threat = current_main_threat
                          + explicit_base_placement
                          + explicit_main_scheme_acceleration
                          + sum(known_enemy_scheme_contributions_against_alter_ego_players)
```

`explicit_base_placement` is already the total placement for the current scenario and
player count when that is what the explicit source reports. `explicit_main_scheme_acceleration`
includes the main-scheme acceleration and every active side-scheme acceleration that
the state explicitly says applies to the main scheme. Add only known villain/minion
scheme values for players currently in alter-ego form. Do not add hidden boost cards,
unknown card text, or guessed modifiers.

Call the result a **minimum**, not a prediction of every villain-phase outcome:
unknown boosts or later effects can increase the actual threat. If the target, base
placement, an applicable acceleration value, or a required alter-ego enemy scheme
contribution is unknown, state the missing value and refuse to claim an exact minimum
clock or exact safety result. Refuse to claim an exact clock when a required target or
gain is unknown; if all required terms are explicit, compare the sum with `target_threat`:

- `minimum_next_main_threat >= target_threat`: flag deterministic next-phase
  main-scheme lethal risk before ending the player phase.
- A smaller margin means threat control is urgent; do not trade it for damage merely
  because the villain's damage clock looks attractive.
- A wide margin permits damage or board development only after the side-scheme effects
  and any current hero-survival requirement are addressed.

Recompute after clearing or adding a side scheme, changing form, changing available
thwart, changing the main-scheme threat, or learning an explicit value. The old
projection is stale after any of those changes.

### Deterministic 9/14 checkpoint

For a normalized state showing `sharedMainScheme[0].tokens.threat = 9` and
`tokens.target_threat = 14`, suppose the explicit next-phase values are:
`base_placement = 2`, `main-scheme acceleration = 1` (for example, from an active
side scheme), and one known alter-ego enemy scheme contribution of `2`. The minimum is:
For the deterministic Rhino-shaped multi-scheme read, keep the cards separate and rank
their actual effects rather than adding their threat values:

| Rank in the 9/14 risk line | Active card | Current tokens | Reason |
| --- | --- | --- | --- |
| 1 | Crowd Control | `threat=3`, `crisis=1` | Crisis blocks player-card removal from the main scheme. |
| 2 | Highway Robbery | `threat=5`, `acceleration=1` | The explicit acceleration adds to the next main-scheme placement. |
| 3 | Breakin' & Takin' | `threat=4`, `hazard=1` | Hazard adds encounter pressure, but not a guessed threat amount. |

This ordering is conditional on the 9/14 line needing main-scheme control; if the current
board supplies a different explicit clock or a legal answer, report the changed reason
and re-rank from the observed indicators.

```text
9 + 2 + 1 + 2 = 14
```

Report **WARNING: minimum next-villain-phase threat reaches 14/14; deterministic
main-scheme lethal risk** before reporting the player phase complete. If an active
`tokens.crisis` side scheme is also present, state that player-card main-scheme
removal is blocked and name the side scheme that must be cleared or resolved. If any
of the four added terms is unknown, report the unknown instead of asserting that this
checkpoint is safe or lethal.

## Attack versus threat control

Use the minimum projection and side-scheme ranking to choose the next legal play:

- **Threat reaches the target on the minimum:** control threat first. Clear or resolve a
  Crisis blocker, remove side-scheme threat, or use another explicitly legal effect.
  Do not pretend a player-card thwart can remove main-scheme threat through Crisis.
- **Threat is close but below the target:** favor the largest explicit clock reduction
  and re-read state after it. Keep enough resources for a known defense or required
  side-scheme answer.
- **Threat has a demonstrated margin:** push villain damage or develop the board only
  when no higher-ranked side-scheme effect and no survival requirement is being ignored.

When you defer a side scheme, use this report shape:

```text
Deferred: <name> — current threat=<value>; effects=<non-zero indicators>.
Reason: <current-state fact>, so <named higher-ranked line> is required first.
```

For example: `Deferred: Breakin' & Takin' — current threat=4; effects=hazard=1.
Reason: current thwart=2 is reserved to clear Crowd Control's crisis=1 blocker before
the 9/14 clock reaches 14/14.` Never write only “handle it later,” “not important,”
or another reason that cannot be checked from the current state.

## The two clocks

**Their clock — threat.** Use the explicit minimum above. If the target or a required
gain is unknown, report the missing value rather than calculating `rounds_until_loss`
from a guessed denominator. When every term is known and the gain is positive:

```text
rounds_until_loss = (target_threat - current_threat) / minimum_threat_gain
```

This is a minimum clock: hidden boosts and later effects can shorten it. A zero known
gain does not prove safety; state whether an unreported gain remains unknown.

**Your clock — damage.** Check `mode` before calculating anything: `mode=win` or
`mode=loss` is terminal and takes precedence over a stale damage or threat report. When
the mode is non-terminal, identify the active stage as `zones.sharedVillain[0]`. Its
current-stage remaining HP is:

```text
current_stage_remaining = authoritative villainHitPoints
                         - sharedVillain[0].tokens.damage
```

`villainHitPoints` is the total for the **current stage only**; it is never cumulative
victory damage. Require both numeric values when claiming an exact current-stage result.
A missing `villainHitPoints`, active villain, or required damage token is unknown; do not
turn it into zero.

### Full villain path, not just the current stage

After reading the active stage, identify every later stage from visible, non-`HIDDEN`
entries in `zones.sharedVillainDeck` when that normalized zone is supplied. For each
visible stage, use its authoritative HP when present or perform an explicit card/rules
lookup for the known scenario, stage, and player-count context. A card name alone,
remembered Rhino values, or a guessed mode multiplier is not a stage HP value. If a later
stage is indicated but hidden, or if the deck zone is absent and no explicit lookup
establishes that the active stage is final, report the later-stage requirement as
unknown and refuse to call the full victory distance or race safe.

When every remaining stage is known, calculate each stage separately:

```text
full_villain_damage = current_stage_remaining
                    + stage_2_remaining
                    + ...
                    + final_stage_remaining
```

Excess damage does not carry from one stage to the next, so a current-stage defeat does
not finish the path by itself. Compare `full_villain_damage` with only realistic legal
damage from the current board, hand, and explicit resources. Use:

```text
rounds_until_win = full_villain_damage / credible_damage_per_round
```

Only call this a credible race when every stage and the repeatable damage line are known.
Recompute after a stage advances, a damage action changes the board, a card/resource is
spent, or any later-stage lookup becomes available.

For example, Rhino I at an authoritative 19 current-stage HP with Rhino II still
remaining is not a 19-damage victory. If an explicit lookup reports 15 HP for Rhino II,
the known path is `19 + 15 = 34`; the agent must compare 34 with its credible legal
damage and must not stop after defeating Rhino I.

### Survival is a team-risk input

Before choosing a race, inspect every seated entry in `players` and its identity in the
corresponding `zones["playerNPlay1"]`. For each seat, derive:

```text
remaining_hero_hp = players.<playerN>.hitPoints
                 - identity.tokens.damage
```

Use only explicit numeric values; a missing player, identity, HP, or damage value is
unknown and must be reported rather than treated as zero. Positive low HP is a major
team-risk input, not automatic game over. A hero is defeated only when its authoritative
remaining HP is zero or less; game loss requires the authoritative terminal state or all
players being eliminated.

Read explicit incoming villain/minion attack or scheme values, explicit modifiers, and
the legal defense, healing, ally-block, alter-ego, and resource lines currently available.
Do not invent boost damage, a probability, a resource count, or a card effect. Compare:

- **Race value:** the complete known villain path that the current legal board and
  resources can finish before the next threat or survival window.
- **Survival value:** the explicit team value of keeping a low-health hero alive and
  preserving the defenses, healing, thwart, or resources that prevent the known loss line.

If a known next villain phase can defeat a positive-HP hero, or the race would spend the
only explicit defense/healing line, the expected team loss outweighs the race value unless
the complete race demonstrably finishes first. Choose the legal survival line and report
the hero's remaining HP, the known incoming value, the resource/board fact, and why it
outranks damage. If the full race is not known or cannot finish before that window,
switch to survival or the highest-value threat-control line; never continue a
current-stage-only race because its HP looks small.

When the hero is safe and every stage, threat term, board obligation, and damage/resource
line is explicit, a credible damage race may continue. Otherwise state the unknown and
replan; do not call uncertainty safety.

When the projected threat clock changes, replan the damage-versus-threat choice; never
continue a damage line based on the previous snapshot.

## Side schemes and minions still compound

Anything in your assigned engaged area is a compounding problem:

- Side schemes with explicit acceleration, Crisis, Hazard, denial, or urgent threat
  outrank an ordinary damage line when their current effect changes the clock or blocks
  the required answer. Clear one only when the observed board confirms it is gone.
- Minions attack or scheme during every villain phase and block you from attacking the
  villain. Kill them when the current threat projection permits it, unless the villain
  is one hit from dying or another explicit blocker is more urgent.

Check both the shared side-scheme zone and your assigned engaged zone every turn.

## When to flip to alter-ego

Flip when **all** of:

- Your remaining HP (`hitPoints` − `tokens.damage`) is below roughly half your maximum.
- You can afford to give up a hero-form turn — i.e. the recomputed threat clock is not
  about to run out and no Crisis-blocked answer is being abandoned.
- Your alter-ego `recover` value meaningfully closes the gap. Recovering 2 when you took
  4 last round is treading water.

Flip immediately if remaining HP is at or below the villain's explicitly known attack plus
any explicitly reported modifier; hidden boost icons remain unknown, so do not declare a
safe line from them. One defeated hero is eliminated, but game loss occurs only when all
players are eliminated or normalized `mode=loss`.

Do not flip when:

- A minion is engaged with you. Alter-egos cannot defend well and you cannot attack it
  back.
- You are the only player able to thwart and the recomputed main-scheme clock is close
  to target.
- Your alter-ego side has a big draw or resource ability you cannot use profitably this
  turn.

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
- Look at your discard: it tells you what your deck has already given you and what is
  left.

Rough shape: rounds 1–2 develop the board with cheap permanents, rounds 3+ convert the
board into damage or thwart every turn while paying for one impactful card.

## Board development

Cards in your assigned play area that exhaust for value are the engine. Each one is a
free action every round for the rest of the game. Ordering:

1. Permanents that generate resources or cards.
2. Allies with useful stats and abilities.
3. Upgrades that raise your ATK / THW / DEF.
4. One-shot events, played when they swing a specific turn.

An ally is worth roughly its `health` in blocked damage plus its stats every round. Do
not throw allies away chump-blocking early unless the alternative is your own defeat.

## Efficiency checklist before you stop

Run this before you report your turn done:

- Is my identity exhausted? If not, is there a reason (holding it to defend)?
- Is every ally and support with a usable ability either exhausted or deliberately held?
- Did I clear everything in my assigned engaged area that I could?
- Did I re-read and rank every active `zones.sharedSideSchemes` card?
- Did I recompute the minimum next-villain-phase threat from the final board?
- Did I leave threat on a side scheme I could have finished, and if so did I report its
  current threat/effects and a current-state reason?
- If the final projection reaches target, did I report the deterministic lethal-risk
  warning and any Crisis blocker before saying the phase is complete?
- Do I have a card in hand I can still afford?
- Did I apply every "Response:" and "Action:" I triggered?

Wasted readiness is the single most common way an agent plays badly here — nothing in the
harness reminds you that a card is still available. End by reporting your board facts and
the reason for any deliberate hold or deferral; never advance the phase yourself.

## Holding back deliberately

Two legitimate reasons to end a turn with a ready card:

1. **Defense.** Keeping your hero ready lets you defend during the villain phase, which is
   usually worth more than a basic attack if the incoming attack exceeds your remaining HP.
2. **Interrupts and responses.** An ally or upgrade whose ability triggers during the
   villain phase must be ready then.

Say so in your report so the coordinator knows the readiness is intentional.
