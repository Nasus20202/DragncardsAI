## 1. Observable threat-clock strategy

- [x] 1.1 Replace the generic side-scheme heuristic in `skills/marvel-champions-play/resources/strategy.md` with normalized `sharedMainScheme`/`sharedSideSchemes` inspection and effect-aware ranking for Crisis, Hazard, acceleration, explicit hand/resource denial, and current threat; verify the reference names every canonical field and distinguishes each effect.
- [x] 1.2 Add the explicit minimum next-villain-phase threat formula, known alter-ego enemy-scheme contributions, target/gain unknown refusal, and attack-versus-threat-control replanning rule; verify deterministic arithmetic and missing-input behavior in the focused regression test.
- [x] 1.3 Add current-state deferral report requirements and the explicit 9/14-to-14/14 lethal-risk checkpoint before ending the player phase; verify the warning and required reason fields in the focused regression test.

## 2. Focused regression coverage

- [x] 2.1 Add `services/agent-orchestrator/tests/unit/test_marvel_strategy.py` with a normalized multi-side-scheme fixture and deterministic assertions for distinct effect ranking, Crisis blocking main-scheme removal, threat projection, unknown-input refusal, and deferred-reason reporting; verify with the single test file only.
- [x] 2.2 Validate the completed OpenSpec artifacts and all focused strategy regressions; verify with `openspec validate dra-81-threat-clock-planning` and the targeted pytest command, without running project-wide validation.
