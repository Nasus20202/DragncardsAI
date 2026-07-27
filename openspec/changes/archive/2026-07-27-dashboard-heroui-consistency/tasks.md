## 1. Audit

- [x] 1.1 Enumerate every raw interactive element (`<button>`, `<input>`, `<select>`, `<textarea>`, `<table>`) and hand-rolled widget (spinner, badge, progress bar, modal, drawer, banner) under `services/dashboard/app` and `services/dashboard/features`.
- [x] 1.2 Confirm the Hero UI 3.2 equivalent and its jsdom DOM shape for each (`Button`, `Checkbox`, `Radio`/`RadioGroup`, `Select`, `SearchField`, `TextField`+`Input`/`TextArea`, `Table`, `Card`, `Alert`, `Chip`, `Spinner`, `ProgressBar`, `Modal`, `Drawer`).

## 2. Shell, Games, Swagger, shared components

- [x] 2.1 `features/shell/components/app-shell.tsx` — theme toggle `<button>` → `Button`.
- [x] 2.2 `features/games/components/games-session-list.tsx` — row `<button>` → `Button`.
- [x] 2.3 `features/games/components/games-workspace.tsx` — loading text → `Spinner`, error text → `Alert status="danger"`.
- [x] 2.4 `features/games/components/dragncards-iframe.tsx` — configuration error → `Alert status="danger"`.
- [x] 2.5 `features/swagger/components/swagger-workspace.tsx` — error `Card` and partial-load notice → `Alert`.
- [x] 2.6 `features/shared/components/collapsible-card.tsx` — header `<button>` → `Button`, body container → `Card`.
- [x] 2.7 `features/shared/components/right-drawer.tsx` — reimplement on Hero UI `Drawer` keeping the existing props.

## 3. Play feature

- [x] 3.1 `play-session-list.tsx` — new/collapse/select/remove `<button>`s → `Button`.
- [x] 3.2 `play-prompt-box.tsx` — `<textarea>` → `TextField`+`TextArea`, send/cancel `<button>`s → `Button`.
- [x] 3.3 `play-transcript.tsx` — collapsible headers, settings toggle, jump-to-latest → `Button`; blocks → `Card`; error banner → `Alert`.
- [x] 3.4 `subagent-card.tsx` / `subagent-list.tsx` — inline SVG spinners → `Spinner`, `<button>`s → `Button`, containers → `Card`.
- [x] 3.5 `subagent-output-modal.tsx` — hand-rolled overlay → `Modal` family.
- [x] 3.6 `toggle-info-row.tsx` — info `<button>` → `Button`.
- [x] 3.7 `context-health-widget.tsx` — hand-rolled bar → `ProgressBar`, "Memory off" pill → `Chip`.
- [x] 3.8 `play-workspace.tsx` — providers notice → `Alert status="warning"`, streaming pill → `Card`.

## 4. History feature

- [x] 4.1 `history-games-list.tsx` and `history-nav-tree.tsx` — `<button>`s → `Button`.
- [x] 4.2 `history-scorecard.tsx` — `<table>` → Hero UI `Table`.
- [x] 4.3 `history-transcript.tsx` — all `<button>`s → `Button`, event/actions containers → `Card`.
- [x] 4.4 `history-workspace.tsx` — search `<input>` → `SearchField`+`Input`, queue badge → `Chip`, delete dialog → `Modal`, error → `Alert`.
- [x] 4.5 `evaluation-control.tsx` — radios → `RadioGroup`/`Radio`, force checkbox → `Checkbox`, seq inputs → `TextField`+`Input`, banners → `Alert`.
- [x] 4.6 `judge-config.tsx` — `<select>`s → `Select`, checkboxes → `Checkbox`, `<textarea>` → `TextArea`, number input → `Input`.
- [x] 4.7 `restore-control.tsx` — radios → `RadioGroup`/`Radio`, outcome banners → `Alert`.
- [x] 4.8 `evaluation-queue.tsx` and `board-control.tsx` — error banners → `Alert`, request rows → `Card`.

## 5. Styling cleanup

- [x] 5.1 `app/globals.css` — drop the `label:has(> input[type=radio|checkbox])` cursor rules that no longer match any markup.

## 6. Tests and verification

- [x] 6.1 Update co-located `__tests__` selectors for the new Hero UI DOM shape without weakening assertions.
- [x] 6.2 `pnpm lint` passes.
- [x] 6.3 `pnpm typecheck` passes.
- [x] 6.4 `pnpm test` passes.
- [x] 6.5 `pnpm build` passes.
- [x] 6.6 `./scripts/lint.sh --fix` passes at the repository root.
