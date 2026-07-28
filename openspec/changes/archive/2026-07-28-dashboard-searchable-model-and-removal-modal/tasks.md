## 1. Shared searchable picker

- [x] 1.1 Extract the Play settings panel's local `ComboSelectField` body into a
      shared `ComboSelect` component in `features/shared/components/`, exposing
      the filter predicate as `filterComboSelectItems` so it can be tested
      directly.
- [x] 1.2 Reduce `ComboSelectField` in `play-config-panel.tsx` to its label
      wrapper plus the shared control, leaving Play's rendered output unchanged.
- [x] 1.3 Hold the typed query in its own state (`null` = mirroring the committed
      value) instead of mirroring the value into state and resyncing it in an
      effect keyed on the caller's item array, which dropped the query whenever
      the owning panel re-rendered.

## 2. History judge model selection

- [x] 2.1 Replace the judge model `<select>` in `judge-config.tsx` with
      `ComboSelect`, keeping the `judge-model` test id on the control's input and
      the surrounding label markup and classes intact.
- [x] 2.2 Keep a drafted model the provider does not offer at the head of the
      offered items, matching the fallback `<option>` the select rendered, and
      keep the control disabled when no models are available.
- [x] 2.3 Leave the judge provider select, reasoning controls, prompt textarea,
      and skills multiselect untouched.

## 3. Session-removal confirmation

- [x] 3.1 Add `RemoveSessionModal` in `features/play/components/` — a HeroUI
      `Modal` naming the session, with Cancel and a danger-styled Remove.
- [x] 3.2 Replace the `window.confirm` call in `play-workspace.tsx` with
      removal-target state that opens the modal; terminate only on confirm.
- [x] 3.3 Leave the session-list removal trigger exactly as it renders today.

## 4. Tests

- [x] 4.1 `combo-select.test.tsx`: filter predicate cases plus rendered
      behaviour — opening offers the full list, typing narrows it, choosing an
      option commits, typing alone does not, and a re-render of the owner that
      rebuilds `items` keeps the typed query.
- [x] 4.2 `judge-config-model-picker.test.tsx`: searching the judge model narrows
      the provider catalogue and the selection propagates into the judge draft; a
      drafted model outside the catalogue stays selectable; the control is
      disabled with no providers.
- [x] 4.3 `play-workspace-removal.test.tsx`: the confirmation names the session
      and removes nothing until confirmed, cancelling leaves the session in
      place, and the existing confirm-path assertions go through the modal.
- [x] 4.4 Extend the Hero UI mock in `play-workspace-test-support.tsx` with the
      `Modal` compound parts and `Button`; add a shared `installResizeObserver`
      test shim so real Hero UI popovers render under jsdom.

## 5. Verification

- [x] 5.1 `pnpm lint`, `pnpm typecheck`, `pnpm test`, and `pnpm build` pass in
      `services/dashboard/`.
- [x] 5.2 `./scripts/lint.sh --fix` passes at the repo root.
- [x] 5.3 Browser check against the running stack: searching `deepseek` in the
      Evaluate drawer's judge model narrows the OpenRouter catalogue to its 11
      matches and selecting one commits it; the Play settings model picker still
      filters; the session-removal modal names the session and cancelling leaves
      the list untouched.
