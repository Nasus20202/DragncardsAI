# Toggle control click + eval-service container boot fixes

## Why

End-to-end verification of the branch (Playwright + CI) surfaced two defects:

- **Dashboard (correctness)** — session-config toggles (`ToggleInfoRow`,
  used for the reasoning stream, skills, and MCP switches) only flipped when the
  user clicked the text label. Clicking the visible switch control did nothing,
  because in HeroUI 3 `Switch.Content` is the clickable `SwitchButton` while
  `Switch.Control`/`Switch.Thumb` are plain spans; the control was rendered as a
  sibling of `Switch.Content` and therefore sat outside the clickable area.
- **eval-service (correctness / CI)** — the `run-tests` CI job failed at the
  "Start Docker stack" step with `eval-service ... is unhealthy`. The service
  crash-looped on import: `config.py` computed its default skill root as
  `Path(__file__).resolve().parents[4] / "skills"`, but only `src/` is copied
  into the image (to `/app/src`), a shallower tree where `parents[4]` raises
  `IndexError`. The image also never packaged the shared `skills/` directory, so
  even a non-crashing default would point at a missing path.

## What Changes

- **dashboard (ToggleInfoRow)** — nest `Switch.Control` inside `Switch.Content`
  so the entire row, including the visual toggle, is clickable; move the
  row-layout classes onto `Switch.Content`.
- **dashboard (test)** — make the `@heroui/react` Switch mock faithful
  (`Switch.Content` is the only clickable element) and add a regression test
  asserting a click on the control toggles the switch.
- **eval-service (config)** — guard the skill-root default so importing
  `config.py` never indexes past the available parents; the packaged image sets
  `SKILL_ROOTS` explicitly, so the computed default only applies to the dev
  layout.
- **eval-service (Dockerfile)** — `COPY skills ./skills` and set
  `ENV SKILL_ROOTS=/app/skills`, mirroring the agent-orchestrator image, so the
  service boots healthy and resolves rules-skill names in the container.

## Out of scope

- The agent-orchestrator image's own skill-root env wiring is unchanged.
- The eval-service's pinned `uv` version is left as-is.
