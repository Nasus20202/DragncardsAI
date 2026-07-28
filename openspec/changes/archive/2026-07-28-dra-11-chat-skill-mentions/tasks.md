# Tasks

## 1. Investigate the existing skill-assignment path

- [x] 1.1 Confirm the settings panel's skill toggles write `draft.selectedSkills`
      and that `saveConfiguration` is what turns that into
      `POST/DELETE /sessions/{id}/skills`.
- [x] 1.2 Confirm `toggleMcp` is the existing pattern for an assignment applied
      immediately rather than on Save, and model skill attachment on it.
- [x] 1.3 Confirm the orchestrator's session skill endpoints already register an
      on-disk skill on enable and treat disable as idempotent, so no service
      change is needed.

## 2. Mention parsing

- [x] 2.1 Add `features/play/lib/skill-mentions.ts` with mention detection from
      text plus caret, token removal, and option filtering that reuses the shared
      `filterComboSelectItems` match.
- [x] 2.2 Add `features/play/__tests__/skill-mentions.test.ts` covering: trigger
      at start of text, trigger after whitespace, no trigger mid-word, query
      capture, caret before the token, whitespace ending a mention, token
      removal, attached skills excluded, and case-insensitive filtering.

## 3. Composer picker and chips

- [x] 3.1 Add `features/play/components/skill-mention-picker.tsx` — a listbox
      popup that keeps focus in the textarea (`aria-activedescendant`), styled
      like the workspace's other floating panels.
- [x] 3.2 Extend `PlayPromptBox` with the available skills, the attached skills,
      and attach/detach callbacks; render the chip row and the picker, and handle
      ArrowUp/ArrowDown/Enter/Tab/Escape without breaking Enter-to-send.
- [x] 3.3 Add `features/play/__tests__/play-prompt-box-skills.test.tsx` for the
      composer behaviour.

## 4. Shared skill assignment

- [x] 4.1 Add `toggleSkill` to `usePlaySession`, modelled on `toggleMcp`: call
      `addSkill`/`removeSkill`, refresh the selected session, and update only the
      mentioned skill in `draft.selectedSkills`.
- [x] 4.2 Wire `skills`, `draft.selectedSkills`, and `toggleSkill` from
      `PlayWorkspace` into `PlayPromptBox`.
- [x] 4.3 Add `features/play/__tests__/play-workspace-skill-attachment.test.tsx`
      proving both directions stay consistent and that attach/detach persists
      immediately.

## 5. Verification

- [x] 5.1 `./scripts/lint.sh --fix` clean.
- [x] 5.2 `./scripts/test.sh unit` passes.
- [x] 5.3 `pnpm typecheck && pnpm build` clean in `services/dashboard`.
- [x] 5.4 `openspec validate --all` reports the same pass count as before the
      change (the pre-existing `spec/typed-game-actions` failure aside).
- [x] 5.5 Sync `openspec/specs/dashboard/spec.md`.
