## 1. Establish what the two passes actually disagree about

- [x] 1.1 Confirm `describePersonaDraftProblem` is pure over the draft — no `window`, `localStorage`, `Date`, randomness, or fetched data — so the server pass and the hydration pass compute the same string from `createEmptyPersonaDraft()`
- [x] 1.2 Fetch the server-rendered `/personas` HTML and record what the Save button carries: `next dev` emits `type="button" disabled="" … data-disabled="true"`, and no `tabindex`
- [x] 1.3 Rule out the component library: `disabled` is produced only by `useButton`'s `{ type, disabled: isDisabled, … }` in react-aria 3.50.0, and nothing in @heroui/react 3.2.3 → react-aria-components 1.19.0 → `useButton` varies between passes (`useIsSSR` reaches only `useInteractionModality` and the `useId` prefix)
- [x] 1.4 Decode the reported diff against react-dom 19.2.8: `added()`/`+` is the client and `removed()`/`-` is the server, and `disabled` runs through `hydrateBooleanAttribute`, whose reported server value is `getAttribute("disabled")` — so `disabled={null}` means the hydrated document carried no such attribute
- [x] 1.5 Establish that `isDisabled` itself did not differ: react-aria emits `data-disabled` from the same value, React does flag an absent `data-*` boolean, and `data-disabled={true}` is absent from the reported diff
- [x] 1.6 Reproduce the consequence: serving `/personas` with only `disabled=""` stripped hydrates to a button that is `data-disabled="true"` yet `button.disabled === false` — React does not patch the mismatch up, leaving a live control that renders as disabled
- [x] 1.7 Record the conclusion: the mismatch is over the presence of a `disabled` attribute in the hydrated document, and the fix is to stop putting a validation-derived `disabled` into the server-rendered HTML at all

## 2. Per-field validation in the persona lib

- [x] 2.1 Add `PersonaDraftProblems` to `features/personas/lib/personas.ts` with one nullable message per validated field: `name` and `systemPrompt`
- [x] 2.2 Add `describePersonaDraftProblems(draft)` reporting the name's problem and the prompt's problem independently, so a draft with two problems states both
- [x] 2.3 Derive `describePersonaDraftProblem(draft)` from `describePersonaDraftProblems`, preserving its existing first-problem order and messages so `save()` and its callers are unchanged
- [x] 2.4 Keep the over-limit message a prompt-field problem, so the standalone paragraph in the editor has an owner to move to

## 3. An error slot on the shared fields

- [x] 3.1 Add an optional `error` prop to `TextInputField` in `features/shared/components/form-fields.tsx`, rendering it under the control as danger-coloured text
- [x] 3.2 Add the same `error` prop to `TextareaField`
- [x] 3.3 Give the message a stable id derived from the field's `id`, set `aria-describedby` on the control to it, and set `aria-invalid` on the control while the error is present
- [x] 3.4 Mark the message `role="alert"` so a problem that appears while typing is announced rather than only seen
- [x] 3.5 Confirm every existing caller renders identically — the prop is optional and unset everywhere else

## 4. The persona editor

- [x] 4.1 Change the Save button to `isDisabled={isBusy}` so no validation-derived `disabled` attribute reaches the server-rendered HTML
- [x] 4.2 Compute `describePersonaDraftProblems(draft)` in the editor and pass the name's problem to the name field and the prompt's problem to the prompt field
- [x] 4.3 Gate the messages on the user having engaged with the form — the first edit to the draft, or an attempted save — so an untouched "New persona" form is not pre-marked as wrong
- [x] 4.4 Reset that gate when a new draft is started and when an existing persona is loaded for editing
- [x] 4.5 Remove the standalone `persona-prompt-over-limit` paragraph now that the prompt field states the same fact
- [x] 4.6 Confirm `save()` still refuses an invalid draft and reports the problem, so an enabled button cannot submit one
- [x] 4.7 State a refused press's reason beside the Save button, referenced by the button's `aria-describedby`, and clear it as soon as the draft can be saved
- [x] 4.8 Stop a refused save writing the problem into the page-level error line, so that slot stays the orchestrator's reply to a request the editor actually made

## 5. Tests

- [x] 5.1 Unit test `describePersonaDraftProblems` for each cause: missing name, malformed name, missing prompt, over-limit prompt, and a draft with a name problem and a prompt problem at once
- [x] 5.2 Unit test that `describePersonaDraftProblem` still returns the same first-problem strings it did before
- [x] 5.3 Component test that a save attempt on an empty form shows the missing-name message at the name field and does not call the orchestrator
- [x] 5.4 Component test each problem's message appearing at its own field while typing: malformed name, missing prompt, over-limit prompt
- [x] 5.5 Component test the accessibility wiring: the offending control carries `aria-invalid` and an `aria-describedby` resolving to the message
- [x] 5.6 Component test the edit path: clearing the prompt of a loaded persona shows the prompt's problem, so the gap is not only on the create path
- [x] 5.7 Regression test for the hydration fix: rendering the editor to static server markup produces a Save button with no `disabled` attribute — verified to fail when `isDisabled` carries the validation term again
- [x] 5.8 Update the existing over-limit test, which asserted the Save button is disabled, to assert the message instead
- [x] 5.9 Component test the refused-press summary: it appears beside the button, the button's `aria-describedby` resolves to it, and it goes away once the draft is saveable
- [x] 5.10 Component test that an untouched new-persona form carries no `aria-invalid`, no `aria-describedby`, and no summary

## 6. Verification

- [x] 6.1 `./scripts/lint.sh --fix`
- [x] 6.2 `pnpm typecheck` in `services/dashboard`
- [x] 6.3 `./scripts/test.sh unit`
- [x] 6.4 `openspec validate --all`
- [x] 6.5 Load `/personas` in a real browser and confirm the console carries no hydration warning, the Save button is pressable, and pressing it on an empty form shows the name field's message and the summary beside the button
