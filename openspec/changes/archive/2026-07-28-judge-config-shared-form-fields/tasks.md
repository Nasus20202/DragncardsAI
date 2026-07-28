## 1. Shared field components

- [x] 1.1 Move `toggle-info-row.tsx` from `features/play/components/` to
      `features/shared/components/` unchanged, and repoint `mcp-section.tsx`,
      `play-config-panel.tsx`, and the toggle row's test at the new path.
- [x] 1.2 Create `features/shared/components/form-fields.tsx` holding the Play
      panel's `FieldLabel`, `TextInputField`, `TextareaField`, `SelectField`,
      `ComboSelectField`, and `SwitchField` verbatim — same JSX, same class
      strings, same props — documented in the style of the other files in
      `features/shared/components/`.
- [x] 1.3 Move the Play panel's skills list into the same module as
      `SkillToggleList`, keeping its heading, border, gaps, and per-skill info
      popover exactly as Play renders them.
- [x] 1.4 Add only the optional pass-throughs the judge panel needs, each of
      which renders nothing when omitted: `inputTestId` (text/textarea/combo,
      mirroring `ComboSelect`), `triggerTestId` (select), `ariaLabel` defaulting
      to `label`, `disabled` on the text and textarea fields, `placeholder` on
      the textarea field, `testId` on `ToggleInfoRow`, and container/per-skill
      test ids on `SkillToggleList`.
- [x] 1.5 Import the wrappers into `play-config-panel.tsx` and delete its local
      definitions, leaving the Play Settings panel's rendered output unchanged.

## 2. Judge configuration panel

- [x] 2.1 Render the judge provider as `SelectField` and the model as
      `ComboSelectField`, dropping the local `inputClass`, and keep the provider
      clamp on change, the empty-provider-list fallback entry, and the
      `(unavailable)` provider suffix.
- [x] 2.2 Render reasoning enable as the shared toggle row, effort as
      `SelectField`, and max tokens as `TextInputField`.
- [x] 2.3 Render the prompt/rubric as `TextareaField` with its placeholder, and
      the skills as `SkillToggleList` so each skill's description and metadata
      are reachable from the info popover.
- [x] 2.4 Keep every `judge-*` test id resolving to its control and every
      accessible name as it was, and keep `disabled` propagating to all controls.

## 3. Tests

- [x] 3.1 Rewrite the judge interactions in `evaluation-judge-stream.test.tsx` to
      drive the real HeroUI controls with `userEvent` (open the select, choose the
      option, click the switches) instead of `fireEvent.change` on native
      elements, keeping the assembled request assertion exactly as strict.
- [x] 3.2 Move `toggle-info-row.test.tsx` to `features/shared/__tests__/` with its
      import repointed and its assertions unchanged.
- [x] 3.3 Add coverage that the judge panel renders switch-based reasoning and
      skill toggles, exposes a skill's description through its info trigger, and
      clamps the model when the provider changes.

## 4. Verification

- [x] 4.1 `pnpm lint`, `pnpm typecheck`, `pnpm test`, and `pnpm build` pass in
      `services/dashboard/`.
- [x] 4.2 `./scripts/lint.sh --fix` and `./scripts/test.sh unit` pass at the repo
      root.
- [x] 4.3 Browser check against the running stack: the Evaluate panel's Judge
      section renders the same controls as Play Settings — provider select opens,
      the model combo filters, reasoning and skill switches toggle, the effort
      select opens — and the Play Settings panel is unchanged.
