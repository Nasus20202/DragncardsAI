# Validate Marvel setup integrity and render progress

## User report

> "selected Rhino setup may display default/mismatched engine board, and engine can hang at empty-pending reveal. Scope: game-service Marvel driver/client/tests, vendored engine Docker config/entrypoint or safe patch overlay if needed, orchestrator skills/tests if lifecycle guidance must change. Requirements: validate post-/new engine state against selected setup before returning a session; fail clearly instead of accepting mismatched/default state; remove/disable unsafe engine startup fallback only through repo-controlled config/patch; make render acknowledgement load-bearing with bounded retry and explicit degradation, without inventing options for empty pending seats; test selected setup and empty-reveal advancement."

## Why

The Marvel driver currently treats a successful `GET /new` plus a later render frame as
proof that the selected setup is the game being driven. The engine can instead expose a
stale or startup-fallback scene, so the service can return a session whose board does not
match the scenario and hero-deck ids the caller selected. The engine also requires the
client's render acknowledgement to advance through reveal steps, but the driver treats
acknowledgement as advisory. An empty `ask_players` frame can therefore stall setup, while
the option surface must not fabricate a choice for a seat that is not pending.

## What changes

- Retain the selected scenario and ordered hero-deck document identities at table creation
  and validate the first ready engine world against them before session creation returns.
- Surface a descriptive setup-integrity failure and tear down the failed driver instead of
  accepting a mismatched or default board.
- Disable the vendored engine's unsafe missing-startup-save fallback through the
  repository-owned Docker patch overlay, so a configured startup save failure is explicit
  rather than silently replaced by Rhino versus Spider-Man.
- Make per-seat render acknowledgement retry a bounded number of times, mark the seat
  degraded after exhaustion, and require successful acknowledgement while consuming empty
  pending/reveal frames so the engine can advance.
- Keep empty pending seats as an empty option result; only the engine's actual enumerated
  options may be submitted.
- Add focused driver, engine-overlay, and live integration coverage for selected setup
  validation and empty-reveal advancement.

## Modified capabilities

- `marvel-lcg` — setup identity validation, render acknowledgement liveness, and safe
  startup behavior.
- `game-service` — Marvel driver/client failure semantics and tests.
- `testing` — selected setup and empty-reveal regression coverage.

## Non-goals

- No changes to DragnCards, DRA-70 history behavior, DRA-71 layout behavior, or Marvel
  Champions rules content.
- No invented Marvel options, automatic setup substitution, or cross-platform fallback.
- No general engine rewrite or change to the engine's public game rules.
