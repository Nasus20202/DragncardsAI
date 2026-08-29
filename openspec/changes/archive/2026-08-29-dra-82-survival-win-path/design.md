## Context

The existing strategy reference computes villain damage from the active stage and separately describes threat and hero health. The normalized state contract supplies `mode`, `players`, `zones`, `pendingSeats`, `playRound`, `phase`, and `phaseLabel`; `zones.sharedVillain[0]` is the active stage, its sparse `tokens.damage` is current-stage damage, and `villainHitPoints` is authoritative only as that stage's total. The player skill is content loaded by agents, so this change must remain executable guidance and deterministic content regressions rather than a second runtime planner.

## Goals / Non-Goals

**Goals:**

- Make the full villain victory path explicit, including how visible later stages and explicit card/rules lookup are used without treating a current-stage total as cumulative.
- Make remaining hero health and explicit next-phase damage part of the same race decision as threat, board obligations, and available resources.
- Provide a deterministic branch for terminal state, unknown state, credible race, and survival/threat-control fallback.
- Keep regressions independent of a live game, network, model provider, or hidden card data.

**Non-Goals:**

- No normalized-state producer, schema, platform action, orchestrator round loop, evaluator/history code, or shared rules-reference edits.
- No guessed stage ordering, stage hit points, boost damage, threat gain, hand contents, resource totals, or card effects.
- No claim that a low-health hero is defeated before normalized health or terminal mode establishes defeat.

## Decisions

### Keep the planner in the existing player strategy reference

Add a full-path and survival decision procedure to `skills/marvel-champions-play/resources/strategy.md`, beside the existing threat-clock procedure. It will name the normalized fields, give compact arithmetic and branch conditions, and require a fresh state read after meaningful changes. A dedicated focused test module will read the reference and execute small normalized dictionaries with explicit lookup inputs.

**Alternative rejected:** adding a Python strategy helper or service endpoint. The issue changes what an LLM agent must do from its reference, and a runtime planner would duplicate card interpretation and create a second source of truth.

### Separate current-stage HP from cumulative victory distance

The active stage's remaining HP is `villainHitPoints - zones.sharedVillain[0].tokens.damage`, with `villainHitPoints` explicitly documented as the current stage total. Later stages are counted only when their cards are visible in the normalized villain-deck zone or their stage HP is supplied by an explicit card/rules lookup. The procedure sums current remainder plus each later-stage requirement; it never carries excess damage from one stage into another. A `HIDDEN` entry or missing numeric lookup makes the full path unknown.

**Alternative rejected:** multiplying or otherwise extrapolating the current stage HP. Scenario mode, player count, and stage values vary, and extrapolation would violate the unknown-value contract.

### Use explicit stage records, not names alone

The guidance will instruct the agent to preserve each visible stage's name/identity and obtain its HP from the authoritative state when supplied or from an explicit lookup of the known scenario/stage. A card name alone does not establish ordering or HP. The agent may report a partial lower bound, but it must not call a complete damage race credible until all remaining stages needed for victory are known.

**Alternative rejected:** treating a familiar villain name (for example, Rhino) as a fixed stage sequence. Custom scenarios, expert modes, and player-count scaling make remembered defaults unsafe.

### Make survival a value comparison, not an automatic stop

For each seated hero, compute remaining health only from normalized numeric player maximum and identity damage. A positive but low result is a risk input. Compare explicit incoming attack/scheme pressure and explicit legal defense, heal, ally-block, or alter-ego options with the damage race and threat clock. If the known line defeats a hero before the team can finish its race, or a legal survival line prevents that loss at a greater explicit value, the guidance requires survival/threat control and a report explaining the current-state reason. `mode=win|loss` is checked first; only zero-or-less health or authoritative loss establishes defeat.

**Alternative rejected:** using a fixed HP percentage or declaring game over whenever HP is low. A percentage ignores villain attack, defense options, and team resources; low health is dangerous but not itself terminal.

### Define credibility using all relevant clocks

A race is credible only if every remaining stage is known, legal damage based on current board/resources can finish the path before the explicit threat clock or survival loss window, and no higher-consequence side scheme/minion obligation is ignored. If any required value is unknown, the agent names it and refuses an optimistic safety claim. If the race is not credible, it switches to the highest-value explicit survival or threat-control line and recomputes after the action.

**Alternative rejected:** comparing one turn of damage only with current-stage HP. That is exactly the failure mode where a 19-HP first stage is incorrectly reported as 19 damage from victory.

## Risks / Trade-offs

- DragnCards and marvel-lcg can expose different villain-deck visibility. The procedure treats absent or `HIDDEN` later stages as unknown and requires an explicit lookup rather than assuming the platform's deck shape.
- A visible stage record may omit printed HP or player-count scaling. The guidance preserves that unknown and may produce a conservative stop instead of a race recommendation.
- Incoming villain/minion attack values and defensive outcomes can change during a villain phase or effect frame. The agent must re-read normalized state after meaningful changes; it must not reuse a stale race or survival comparison.
- The WebSocket-backed marvel-lcg render can advance a stage between observations. The active `sharedVillain[0]`, terminal `mode`, and current-stage damage must be re-read before any report; the reference never addresses a hidden or stale stage by guessed identity.
