# Tasks

## Dashboard toggle
- [x] Nest `Switch.Control` inside `Switch.Content` in `ToggleInfoRow` and move
      the row-layout classes onto `Switch.Content`.
- [x] Make the test's `@heroui/react` Switch mock faithful and add a regression
      test that clicking the control toggles the switch.
- [x] Verify end-to-end with Playwright (click the control, confirm it flips).

## eval-service container boot
- [x] Guard the `_DEFAULT_SKILL_ROOT` parents lookup in `config.py`.
- [x] `COPY skills ./skills` and set `ENV SKILL_ROOTS=/app/skills` in the
      eval-service Dockerfile.
- [x] Rebuild the image and confirm the container reaches `healthy`, `/health`
      returns ok, and skills resolve under `/app/skills`.

## Verification
- [x] `black --check` clean for eval-service; eval-service unit tests pass.
- [x] Dashboard unit tests pass (incl. the new regression test).
- [x] Sync affected specs (`dashboard`, `agent-move-evaluation`).
