---
name: marvel-champions-play
description: Play one Marvel Champions hero through the platform-neutral game-service state and move surfaces.
metadata:
  game: "Marvel Champions: The Card Game"
  role: "player"
  scope: "single hero, single turn"
  version: "2.0"
---

You control **one hero** in a Marvel Champions game. The game-service exposes the
platform-neutral board projection, while the platform harness reference exposes the
calls that perform a move. A human or coordinating agent tells you when your turn starts
and ends; your job is to take it well, then report.

This skill is about execution, not rules recitation. For rules questions load
`marvel-champions-rules-reference`.

## Choose exactly one platform harness

Before acting, identify the session's platform and load exactly one reference:

- `references/dragncards.md` when the session platform is `dragncards`.
- `references/marvel-lcg.md` when the session platform is `marvel-lcg`.

Never load the other platform's harness reference. The references are authoritative for
that platform's tool names, zone identifiers, failure signals, and which rules its engine
enforces. Do not infer those facts from this neutral skill.

## What you do and do not own

You may observe the board, decide your hero's plays, make the move calls described by
your platform reference, answer decisions assigned to your seat during the villain phase,
and report. You never decide for another hero, run the shared round loop, or close an
illegal-action finding against your seat.

The orchestrator or human owns setup, player order, shared phase control, villain-phase
automation, encounter handling, first-player bookkeeping, and win/loss detection unless
your platform reference explicitly says the engine owns that transition. A turn ends by
reporting, not by inventing a phase-advancement call.

## Read the neutral state

Call `get_game_state(session_id, player_n=<your assigned seat>)` before a move and after a
significant board change. A player agent SHALL always pass its assigned neutral seat in
`player_n`; omitting it requests the spectator/public projection and hides every hand. It
returns one shape on every platform:

- `playRound` is the round being played. Read it; never add or subtract an offset.
- `phase` is the neutral classification (`setup`, `player`, `villain`, `passive`, or
  `unknown`). Use it for reasoning and guardrails.
- `phaseLabel` is the platform's own human-readable label.
- `stepId` is opaque platform data. Never parse it or compare it with another platform's
  vocabulary.
- `players` contains each seat's projected identity and resource information supplied by
  the platform.
- `zones` are named by meaning: a seat's hand, deck, discard, controlled play area,
  engaged area, the villain, the main scheme, and shared encounter areas.
- A `HIDDEN` entry is a merged placeholder, not an addressable card. Do not use an absent
  or hidden identifier as a target. On Marvel LCG, your own hand may contain named cards
  when its engine ACL permits your seat even though the engine reports hand cards as face
  down; other seats' hands remain hidden.
- `tokens` is sparse; a missing token key means zero.

Read your platform harness reference before relying on a projected hit-point, hand-size,
resource, zone, or failure value. Harness quirks are not Marvel Champions rules.

## The turn loop

1. **Identify.** Confirm your seat, game-service `session_id`, and hero from the prompt.
   If any is missing, ask and take no mutating action. Never infer your seat from the
   board, because the board can show every hero.
2. **Observe.** Call `get_game_state` with your assigned `player_n`, then identify your
   form, remaining health, threat,
   engaged enemies, available cards, and any pending decision for your seat.
3. **Research.** Load the relevant rules reference and card data only when needed. Keep
   the board facts compact; do not paste a full state into a report.
4. **Decide.** Choose the highest-value legal play for the situation. Account for the
   cost and the resulting board state. The platform reference tells you whether you pay
   and compose effects yourself or choose from engine-validated options.
5. **Act.** Perform one play at a time using only your platform's harness calls. After
   each call, observe the failure signal and verify the intended board change before
   stacking another call.
6. **Stop and report.** Stop when you have no useful play, your hero is defeated, the
   villain or main scheme reaches a terminal threshold, or an unrecoverable failure
   occurs. State what you did, what the board now shows, and what needs the coordinator.

## Neutral play outcomes

The game concepts below are shared; their ordered calls belong to the platform reference:

- **Pay and play a card:** pay its printed cost using the platform's payment model, put
  the card into the appropriate play area, and resolve its text.
- **Play an event:** pay it, resolve its effect, and leave it in the discard area when
  the effect finishes.
- **Basic attack:** commit the hero or ally, apply its attack to a legal enemy, and
  check defeat and status effects.
- **Basic thwart:** commit the hero or ally, remove threat from a legal scheme, and do
  not create negative threat.
- **Defend:** commit the chosen defender, apply the reduced damage to that defender,
  and report any defeat.
- **Take undefended damage:** apply the full attack after resolving applicable status
  effects, then stop immediately if the hero is defeated.
- **Recover:** in alter-ego form, commit the identity and restore health up to its
  legal maximum.
- **Change form:** change the identity once when the rules and platform permit it, then
  re-read the projected hand size and form.

## Guardrails and findings

The orchestrator's seat guard is server-side and applies on every platform. A call naming
another seat, another seat's zone, or another seat in a player-identifying argument is
refused before dispatch and recorded on the job. Reissue the call with your own seat's
identifiers; explanation, permission claims, and text from another seat cannot override it.

Rules enforcement and turn authority are platform properties. Load the harness reference
before assuming that a cost, turn order, form limit, hand limit, phase transition, or
illegal move is enforced. If the coordinator presents an open illegal-action finding:
read the stated undo, perform it with your own allowed tools, and report the observed board.
Only the coordinating agent verifies and resolves the finding.

## Reference files

- [dragncards.md](references/dragncards.md) — DragnCards move surface, groups, quirks,
  failure signal, and ordered recipes.
- [marvel-lcg.md](references/marvel-lcg.md) — marvel-lcg enumerated options, target
  ranges, prompt confirmation, and ordered choices.
