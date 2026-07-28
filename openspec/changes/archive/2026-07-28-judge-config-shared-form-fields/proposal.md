# Build the judge configuration from the same field components as Play settings

## Why

A user reported: "In judge options in evaluate window it still uses different
components than model configuration in dashboard. (Should be the same)".

The Play tab's Settings panel and the History tab's Evaluate → Judge panel offer
the same configuration — provider, model, reasoning on/off, reasoning effort,
reasoning max tokens, a prompt textarea, and a skills multiselect — but they are
built from two different control sets:

- `play-config-panel.tsx` defines local field wrappers (`FieldLabel`,
  `TextInputField`, `TextareaField`, `SelectField`, `ComboSelectField`,
  `SwitchField`) over HeroUI `TextField`/`Input`/`TextArea`/`Select` and renders
  each toggle as a `ToggleInfoRow` switch, with skills in a bordered list that
  carries a per-skill info popover.
- `judge-config.tsx` renders raw HTML: a native `<select>` for provider and for
  reasoning effort, `<input type="checkbox">` for reasoning and for every skill,
  `<input type="number">` for max tokens, and a `<textarea>` for the rubric — all
  sharing one ad-hoc `inputClass` string. Only the model picker had already been
  moved onto the shared `ComboSelect`.

So the same settings look and behave differently depending on which tab they are
opened from: different label typography, different borders and focus rings, plain
checkboxes instead of switches, and no skill descriptions (the judge panel only
put the skill name in a `title` attribute).

The root cause is that the field wrappers live inside the Play panel, so nothing
else can use them. That is also why the drift happened in the first place: the
only way for a second panel to render these fields was to hand-roll them.

## What Changes

- **dashboard (shared components)** — promote the Play panel's field wrappers to
  `features/shared/components/form-fields.tsx` and move `ToggleInfoRow` to
  `features/shared/components/toggle-info-row.tsx`, so both panels render from
  one implementation instead of `features/history` reaching into
  `features/play`. The move is a pure extraction: identical JSX, class strings,
  and behavior. The wrappers gain only optional pass-throughs the second
  consumer needs — a test id, an accessible-name override, `disabled`, and a
  textarea placeholder — each of which renders nothing when omitted, so the Play
  panel's output is unchanged.
- **dashboard (shared components)** — the bordered skills toggle list, which both
  panels need identically, moves into that shared module as `SkillToggleList`
  rather than being written twice.
- **game-history-ui (judge panel)** — rebuild `judge-config.tsx` on those
  wrappers: provider as a `SelectField`, model as a `ComboSelectField`,
  reasoning as the switch row, effort as a `SelectField`, max tokens as a
  `TextInputField`, prompt/rubric as a `TextareaField`, and skills as the same
  bordered `SkillToggleList` — including the info popover carrying each skill's
  description and metadata, which the judge panel did not show at all.
- **dashboard (tests)** — the judge tests that drove native `<select>` and
  checkbox elements with `fireEvent.change` now drive the real HeroUI listbox and
  switches with `userEvent`, the pattern the existing judge model-picker test
  already uses.

The judge panel's contract is unchanged: every existing `data-testid` still
resolves to the corresponding control, the accessible names (`Judge provider`,
`Judge model`, `Reasoning`, `Reasoning effort`, `Reasoning max tokens`,
`Custom prompt or rubric`) are preserved, and the existing behavior — clamping
the model when the provider changes, keeping a drafted model the provider does
not offer selectable, honouring `disabled`, and offering the drafted provider id
when the provider list is empty — is untouched.

## Non-goals

- No visual change to the Play Settings panel. It is the reference; the judge
  panel changes to match it, never the reverse.
- No change to the judge draft shape, `assembleJudgeConfig`, or the evaluation
  request payload.
- No restyling of any other dashboard component, and no change to the Evaluate
  panel's scope/target controls.
- Reasoning max tokens becomes a text field like Play's rather than
  `<input type="number">`; the value was already carried as a string and parsed
  on assembly, so no validation behavior is added or removed here.
