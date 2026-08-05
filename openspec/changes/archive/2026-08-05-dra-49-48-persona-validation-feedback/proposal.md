## Why

The persona editor's Save button carries the whole of the form's validation in a
single attribute:

```tsx
<Button aria-label="Save persona" isDisabled={isBusy || problem !== null} …>
```

`problem` is the string `describePersonaDraftProblem` returns — "A persona needs
a name.", "A persona name must be lowercase letters, digits and hyphens…", "A
persona needs a system prompt…", "The system prompt is N characters, over the
8000 limit." — and it is never rendered anywhere. The user is left with a greyed
out button and no statement of what is wrong with the form (DRA-48).

The same expression is what React reports a hydration mismatch on (DRA-49):

```
+ disabled={true}    (client)
- disabled={null}    (server)
```

**The two passes do not evaluate `isBusy || problem !== null` differently.**
`createEmptyPersonaDraft()` is deterministic and `describePersonaDraftProblem`
is pure over the draft — no `window`, storage, `Date`, randomness, or fetched
data — so `problem !== null` is `true` in both. The report itself proves it:
`data-disabled={true}`, which react-aria emits from the *same* `isDisabled`,
does not appear in the diff, and React does flag a missing `data-*` boolean
(`react-dom` 19.2.8, the generic branch of `diffHydratedProperties` returns
`null` for an absent attribute). Only `disabled` diverged.

Decoding that diff against `react-dom` 19.2.8: `+` is the client and `-` is the
server (`added()`/`removed()` in the hydration-diff printer), and `disabled`
goes through `hydrateBooleanAttribute`, whose reported server value is
`domElement.getAttribute("disabled")`. So `- disabled={null}` means **the
document React hydrated against carried no `disabled` attribute**, while the
server's own bytes do carry it — `next dev` serves
`… type="button" disabled="" … data-disabled="true"` for that button. The
attribute was removed from the parsed DOM before React loaded, which is the
last cause React's own message lists.

That leaves a real defect, not a cosmetic warning: React says such a mismatch
"won't be patched up", and it does not patch it up. Serving that page with only
`disabled=""` stripped, everything else identical, hydrates to a button that is
`data-disabled="true"` — styled and reported as disabled — while
`button.disabled === false`, so it is live and clickable.

Encoding validation in `disabled` is what puts a `disabled` attribute into the
server-rendered HTML of a form nobody has touched yet. It is both the thing the
user cannot see through and the precondition for the mismatch: an attribute that
is never emitted cannot be disagreed about, stripped, or left divergent. One
change fixes both.

## What Changes

- **Validation stops driving the `disabled` attribute.** The Save button is
  disabled only while a request is in flight (`isBusy`), which is `false` in the
  server pass and `false` in the hydration pass, so the button is rendered with
  no `disabled` attribute at all and there is nothing for the two passes to
  disagree about. Correctness is unchanged: `save()` already re-checks
  `describePersonaDraftProblem` and refuses an invalid draft before calling the
  orchestrator, so an invalid draft is still never submitted.
- **Every validation problem is attributed to the field that causes it.**
  `describePersonaDraftProblem` today collapses four distinct problems into one
  first-problem string. It gains a per-field sibling,
  `describePersonaDraftProblems`, that reports the name field's problem and the
  system prompt field's problem independently; the existing single-string
  function is derived from it so there remains one source of truth for what
  "cannot be saved" means.
- **The problem is shown at the offending field**, in red, wired for assistive
  technology: the field's control gets `aria-invalid` and an `aria-describedby`
  pointing at the message, and the message is a live region so a problem that
  appears while typing is announced.
- **A press of Save that is refused says so beside the button.** Both current
  problems attribute to a field, but on this form every field is a scroll above
  the button, so a press that submits nothing would otherwise look like a press
  that did nothing. The first outstanding reason is repeated next to the button
  as a live region and referenced by the button's own `aria-describedby`, and it
  clears as soon as the draft becomes saveable. It replaces, rather than joins,
  the page-level error line that a refused save used to write: that slot is for
  what the orchestrator says about a request the editor actually made.
- **The messages appear once the user has engaged with the form** — after the
  first edit to the draft, or after a save is attempted — rather than greeting an
  untouched "New persona" form with two red errors.
- **The prompt's existing standalone over-limit paragraph is folded into the
  prompt field's error slot**, so the same fact is stated once rather than in two
  places with two wordings.
- The shared `TextInputField` and `TextareaField` gain an optional `error` slot
  alongside the `description` slot they already have. No existing caller passes
  it, so no existing panel changes.

## Capabilities

### Modified Capabilities

- `dashboard`: the persona editor states why a draft cannot be saved at the field
  that causes it, and no longer expresses validation through the Save button's
  disabled state.

## Non-goals

- Changing what makes a persona draft valid. The name pattern, the required
  system prompt, and the 8000-character limit are the agent-orchestrator's rules
  and are mirrored, not redefined.
- Restyling, re-theming, or re-laying-out the persona editor or any other panel.
  The only new pixels are the error messages themselves.
- Adding validation feedback to the other configuration panels (Play settings,
  the History tab's judge configuration). They gain the `error` slot as an
  available prop and pass nothing.
- Converting the fields to React Aria's `isInvalid`/`FieldError` mechanism. That
  would change the fields' appearance across every panel that renders them.
- Any change to the agent-orchestrator, its persona API, or its own validation.

## Impact

- `services/dashboard/features/personas/lib/personas.ts` — adds
  `PersonaDraftProblems`/`describePersonaDraftProblems`;
  `describePersonaDraftProblem` becomes a derivation of it.
- `services/dashboard/features/personas/components/persona-editor.tsx` — the Save
  button's `isDisabled` drops the validation term; the name and prompt fields
  render their problem; a refused press states its reason beside the button; the
  standalone over-limit paragraph is removed.
- `services/dashboard/features/shared/components/form-fields.tsx` —
  `TextInputField` and `TextareaField` gain an optional `error` slot with
  `aria-invalid`/`aria-describedby` wiring.
- `services/dashboard/features/personas/__tests__/personas.test.ts`,
  `services/dashboard/features/personas/__tests__/persona-editor.test.tsx` —
  coverage for each problem cause, for the edit path, for the accessibility
  wiring, and a server-render assertion that the Save button carries no
  `disabled` attribute.
