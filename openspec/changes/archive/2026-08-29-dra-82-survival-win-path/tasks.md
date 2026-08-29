## 1. Survival-aware full-villain strategy

- [x] 1.1 Extend `skills/marvel-champions-play/resources/strategy.md` with authoritative current-stage versus later-stage inspection, explicit full-path damage arithmetic, terminal-mode precedence, and unknown-value refusal; verify the guidance names `zones.sharedVillain[0]`, `villainHitPoints`, `tokens.damage`, visible/explicit later stages, and no-guess behavior.
- [x] 1.2 Add executable health-aware race triage to `strategy.md`: derive every hero's remaining health, compare explicit incoming damage and legal survival resources with the threat clock and complete villain path, and switch to survival/threat control when expected team loss outweighs race value; verify low-health, non-terminal, credible-race, and non-credible-race branches are all stated.

## 2. Focused deterministic regression coverage

- [x] 2.1 Add a focused strategy regression module with normalized multi-stage Rhino and low-health hero fixtures; verify assertions fail for current-stage-only victory arithmetic and for ignoring positive-but-near-death hero health.
- [x] 2.2 Mark the OpenSpec tasks complete after running `openspec validate dra-82-survival-win-path` and the single focused pytest module; do not run project-wide validation, formatters, or browser checks.
