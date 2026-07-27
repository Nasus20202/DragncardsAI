## Why

The three skills we ship today (`dragncards`, `marvel-champions-learn-to-play`,
`marvel-champions-rules-reference`) tell an agent what the *rules* of Marvel Champions
are. None of them tell it how to *execute* a turn through the tool surface it is
actually given. The result is an agent that can explain a thwart but cannot perform
one: it does not know that costs are paid by moving cards to `playerNDiscard` itself,
that `players.playerN.hitPoints` is maximum HP rather than remaining HP, that
`success: true` is returned even when the underlying DragnLang aborted, or that
`player_end_phase` mutates every player's board and must never be called by a single
player agent.

Those facts are only discoverable by reading `services/game-service/` source and the
DragnCards Marvel Champions plugin JSON. An agent in a session has neither. It needs a
skill that encodes the harness contract directly.

## What Changes

- **New skill `skills/marvel-champions-play/`** — a harness-grounded player capability
  for a single agent controlling one hero. Covers reading the simplified game state,
  a concrete per-turn decision loop, exact tool-call recipes for every common play,
  verification and recovery procedure, and observable-driven strategy heuristics.
- **Reference files under `skills/marvel-champions-play/resources/`** — five markdown
  references (`reading-state.md`, `tool-reference.md`, `play-recipes.md`,
  `strategy.md`, `recovery.md`) loaded on demand via `load_skill_reference`, mirroring
  how `marvel-champions-rules-reference` structures resources.
- **Explicit non-player boundary** — the skill enumerates the tools a player agent
  MUST NOT call (round/phase automation, encounter dealing, deck loading, session
  lifecycle, other players' zones) so it composes cleanly with a coordinating agent
  that owns those.
- **Known-defect documentation** — `shuffle_into_deck` is recorded as currently
  failing in-game with a documented workaround, and the "`success` is always true,
  read `error`" contract is stated as a hard rule.

No service code, no existing skill, and no runtime behaviour changes. The skill is
discovered automatically from `SKILL_ROOTS` (repo-root `skills/`) and is copied into
the agent-orchestrator image by the existing `COPY skills ./skills` step.

## Non-goals

- Coordinating a multiplayer game (round flow, phase transitions, per-player
  dispatch). That is a separate coordination skill and is deliberately out of scope.
- Deck building, hero selection, or scenario setup.
- Changing the game-service tool surface, the simplified state shape, or fixing
  `shuffle_into_deck`. Those are documented here, not repaired here.
- Automating the villain phase.

## Capabilities

### New Capabilities

- `marvel-champions-play-skill`: The content contract for the player-facing Marvel
  Champions skill — what a session agent is taught about the harness, which tool-call
  sequences it is given, and which operations it is forbidden from performing.

## Impact

- New directory `skills/marvel-champions-play/` (`SKILL.md` + `resources/*.md`).
- New spec `openspec/specs/marvel-champions-play-skill/spec.md`.
- No source changes in `services/`. No database, API, or MCP changes.
- Skill discovery, `load_skill`, and `load_skill_reference` already support this
  directory shape; nothing needs to be registered.
