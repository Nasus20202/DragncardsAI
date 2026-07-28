# Searchable judge model picker and a real confirmation dialog for session removal

## Why

Two rough edges in the dashboard, both in controls the user reaches for often.

The History tab's Evaluate drawer picks the judge model with a plain `<select>`.
The model list comes from the provider catalog, and on an aggregating provider
such as OpenRouter that is hundreds of entries in one native dropdown with no way
to type at it — the only way to reach `anthropic/claude-sonnet-4` is to scroll.
The Play tab already solved this: its settings panel uses a filterable HeroUI
`ComboBox` for the model, so the two model pickers in the same application behave
differently for no reason.

Session removal in the Play session list confirms with `window.confirm`. The
removal control is a hover-revealed `✕` next to each session, so a mis-aimed
click is easy; the browser dialog that catches it is unstyled, cannot name which
session is about to go, and renders outside the application's visual language
next to the styled confirmation the History tab already uses for deleting a
game's history.

## What Changes

- **dashboard (searchable model selection)** — the filterable model control that
  the Play settings panel already renders SHALL be extracted as one shared
  `ComboSelect` component, and the History tab's judge configuration SHALL use it
  for model selection in place of the plain `<select>`. Typing in the control
  SHALL narrow the offered models by case-insensitive substring match; opening it
  SHALL offer the provider's whole catalog; a query that only narrows the list
  SHALL NOT change the drafted model. A drafted model the provider does not offer
  SHALL remain selectable, preserving the fallback the plain select rendered.
  Play's rendered control is unchanged — it keeps its own label wrapper and now
  delegates the control body.
- **dashboard (search survives re-renders)** — the picker SHALL hold the typed
  query in its own state rather than mirroring the committed value into state and
  resyncing it in an effect. The owning panels rebuild their item arrays on every
  render, so the effect form dropped the user's query on any unrelated re-render
  of the panel — visible in the Evaluate drawer as a search box that refused to
  accept typing. This fixes the Play settings panel's model picker at the same
  time, since both now share the control.
- **dashboard (session removal confirmation)** — the Play session list's removal
  control SHALL confirm through a HeroUI `Modal` that names the session being
  removed and offers Cancel alongside a danger-styled Remove action, replacing
  `window.confirm`. Termination SHALL happen only when the danger action is
  pressed; cancelling or dismissing the dialog SHALL leave the session untouched.
  The removal trigger in the session list is unchanged.
- The judge **provider** select, the reasoning controls, the prompt/rubric
  textarea, and the skills multiselect in the judge panel are untouched, as is
  the History tab's existing delete-history confirmation dialog.

## Non-goals

- Any further HeroUI conversion of existing dashboard components. The existing
  dashboard is the visual reference; this change swaps exactly two controls and
  leaves surrounding markup, styling, and `data-testid` values alone.
- Server-side or fuzzy model search, model grouping by provider prefix, or
  recently-used model ordering. Client-side substring filtering over the already
  fetched provider catalog is enough for catalogs of this size.
- A generic confirmation-dialog abstraction. The History tab's delete-history
  dialog keeps its own bespoke markup; unifying the two is a separate decision.

## Impact

- Affected specs: `dashboard` (session-list removal now requires a modal
  confirmation; session configuration controls note the shared searchable model
  control), `game-history-ui` (judge configuration model selection is
  searchable).
- Affected code:
  `services/dashboard/features/shared/components/combo-select.tsx` (new shared
  `ComboSelect`), `services/dashboard/features/play/components/play-config-panel.tsx`
  (its local `ComboSelectField` body moves to the shared component),
  `services/dashboard/features/history/components/judge-config.tsx` (model
  `<select>` → `ComboSelect`),
  `services/dashboard/features/play/components/remove-session-modal.tsx` (new
  confirmation dialog),
  `services/dashboard/features/play/components/play-workspace.tsx`
  (`window.confirm` → modal state).
- No API, schema, or configuration changes.
