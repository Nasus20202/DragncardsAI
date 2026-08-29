## Context

`skills/marvel-champions-play/resources/strategy.md` currently describes a threat clock, but its formula mixes an unavailable `scheme_acceleration` value with a broad "cards in play" sum and treats side schemes as one generic cleanup category. DRA-83 now supplies the normalized inputs this reference can safely consume: `zones.sharedMainScheme[0]`, `tokens.threat`, `tokens.acceleration`, and the public effect indicators on each card in `zones.sharedSideSchemes`. The change remains content-only; no game-service, orchestrator, evaluator, or platform harness code is part of this design.

## Goals / Non-Goals

**Goals:**

- Give a player agent a deterministic inspection order that considers each active side scheme before selecting attack, thwart, or a deferred plan.
- Define a minimum next-villain-phase main-scheme projection from explicit values, with a clear boundary between a valid lower bound and an unavailable exact clock.
- Make Crisis, Hazard, acceleration, hand/resource denial, and current threat actionable without claiming values the normalized state does not report.
- Make the 9/14 Rhino-shaped checkpoint produce a visible lethal-risk warning before the player phase ends.
- Pin the guidance to focused, deterministic content regressions that use normalized state-shaped dictionaries rather than a live table.

**Non-Goals:**

- No new runtime planner, parser, state field, or card-catalog behavior.
- No changes to the shared rules references, platform references, orchestrator prompts, or evaluator/history inputs.
- No conversion of Hazard, denial, or hidden boost effects into guessed damage, card counts, or threat values.

## Decisions

### Keep all behavior in the strategy reference

The executable procedure will be prose plus compact pseudocode and a worked checkpoint in `strategy.md`. The player agent already loads this file as a reference, and putting the rules beside the existing clock heuristics avoids introducing a second strategy source.

**Alternative rejected:** adding a Python helper or service endpoint. A runtime planner would need another state contract, would duplicate card/rules interpretation, and would make a content correction require a deployment rather than a skill update.

### Inspect normalized zones before scoring a plan

The procedure first verifies that an active main-scheme card exists, reads its sparse `tokens.threat`, `tokens.target_threat` when explicitly present, and then iterates every visible card in `zones.sharedSideSchemes`. For each card it records only non-zero public token indicators: `crisis`, `hazard`, `acceleration`, `hand`, `resource`, and `threat`. A missing token key is zero only because the normalized state defines sparse tokens; a missing card or non-numeric required input remains unknown.

**Alternative rejected:** deriving effects from side-scheme names or remembered card text. Names are not an authoritative state source, and hidden/unreported text could cause the agent to act on facts unavailable to its seat.

### Use conditional effect priority, not one fixed threat total

The guidance treats Crisis as an action blocker when the current plan needs player-card removal from the main scheme. It then prioritizes explicit acceleration by its added next-placement amount, Hazard by its reported encounter-pressure indicator, explicit hand/resource denial by the reported indicator, and current side-scheme threat according to the current projected clock and available thwart. The final order is conditional: a currently lethal clock can outrank a lower-pressure effect, and a side scheme that can be cleared now can outrank an otherwise higher but unaffordable one. Every deferred entry must explain that current fact.

**Alternative rejected:** summing all side-scheme threat and sorting only by total. That loses which card blocks the intended action and which card changes the next villain-phase gain.

### Define the next-phase minimum from additive known terms

The reference gives this exact expression:

```
minimum_next_main_threat = current_main_threat
                          + explicit_base_placement
                          + explicit_main_scheme_acceleration
                          + sum(known_enemy_scheme_contributions_against_alter_ego_players)
```

`explicit_base_placement` is already the total placement for this scenario/player count when that is what the coordinator, state, or permitted card/rules lookup reports. `explicit_main_scheme_acceleration` includes each known acceleration token/icon that the state explicitly says applies to the main scheme, including active side-scheme acceleration. Enemy scheme contributions mean known villain/minion scheme values for activations against players currently in alter-ego form; hidden boost cards are not guessed. The result is labeled a minimum because later hidden or optional effects can only increase the actual total. If target, base placement, acceleration, or a required scheme contribution is unavailable or non-numeric, the agent names the missing input and refuses an exact clock or safety claim.

**Alternative rejected:** using a standard one-threat-per-player default or adding a guessed boost value. Scenarios and engine variants differ, and the normalized contract requires preserving unavailable facts rather than fabricating them.

### Pin the deterministic 9/14 warning to explicit arithmetic

The worked checkpoint uses current threat `9`, target `14`, explicit base placement `2`, explicit acceleration `1`, and one known alter-ego enemy scheme contribution `2`. The minimum is therefore `14`, so the reference requires a next-phase lethal-risk warning before the player phase report. The example also carries an active Crisis side scheme, making clear why a direct main-scheme thwart line cannot be silently assumed to work.

**Alternative rejected:** saying only that the scheme is "close" or relying on the current phase label. A numeric warning is reproducible, and phase labels are opaque platform data outside this strategy calculation.

### Test the contract without live-game dependence

A new focused unit file will load `strategy.md`, build a small normalized state with three named active side schemes (Crisis, Hazard, and acceleration), and assert deterministic ranking, Crisis blocking, arithmetic at 9/14, unknown-input refusal, and deferred-reason/reporting language. Assertions tie the state-shape keys and expected named ordering to the reference text, so a content edit that drops a required effect or warning fails without requiring a game engine or provider credentials.

**Alternative rejected:** adding a live integration scenario. The requested regression is deterministic, and a live table would introduce asynchronous state, hidden encounter cards, and external infrastructure unrelated to the content contract.

## Risks / Trade-offs

- The upstream engine can add or rename public effect metadata. The reference therefore treats only canonical normalized keys as actionable and requires an explicit unknown report for anything else.
- A normalized state can be observed between effect frames. The procedure re-reads after meaningful actions and performs the final projection immediately before reporting, so a transient snapshot cannot be presented as a settled clock.
- The minimum projection deliberately does not predict hidden boosts or optional card effects. This can produce a warning earlier than a simple point estimate, but it prevents an unsafe claim that an unknown board is safe.
