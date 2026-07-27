## Why

`services/dashboard/AGENTS.md` requires Hero UI components for every control, and
`openspec/specs/dashboard/spec.md` already states the dashboard uses "HeroUI components for
all controls". Reality had drifted: an audit of every `.tsx` file under `services/dashboard/`
found ~40 raw HTML interactive elements and hand-rolled widgets that Hero UI 3 already
provides — `<button>` in 14 components, native `<input type="radio|checkbox|number|search">`
and `<select>`/`<textarea>` in the History evaluate/judge/restore panels and the Play prompt
box, a raw `<table>` in the player scorecard, two hand-rolled SVG spinners, a hand-rolled
progress bar, a hand-rolled modal, a hand-rolled right-side drawer, and ~20 bespoke
danger/warning/success banner `<div>`s.

The result was inconsistent focus rings, keyboard behaviour, disabled styling, and dark-mode
tints between screens that were converted earlier (`play-config-panel`, `mcp-section`) and
those that never were.

## What Changes

Purely presentational: every raw interactive element and hand-rolled widget in
`services/dashboard/` is replaced with its Hero UI 3 equivalent, keeping rendered behaviour,
`data-testid` values, ARIA roles/labels, and callback contracts identical.

- **Buttons** — `Button` replaces `<button>` in the app shell theme toggle, Games/Play/History
  session and games lists, Play transcript collapsibles and jump-to-latest, prompt box
  send/cancel, subagent list/card/modal, the shared collapsible card, the History nav tree,
  transcript field/conversation/evals/actions toggles, and the transcript toolbar.
- **Form fields** — `RadioGroup`/`Radio` replace the evaluate-scope, evaluate-target, and
  restore-mode radio sets; `Checkbox` replaces the force-re-evaluate, judge-reasoning, and
  judge-skill checkboxes; `Select` replaces the judge provider/model/effort `<select>`s;
  `TextField` + `Input`/`TextArea` replace the seq-range, reasoning-max-tokens, judge-prompt,
  and Play prompt fields; `SearchField` + `Input` replaces the transcript search box.
- **Containers and feedback** — `Card` replaces bespoke bordered container `<div>`s;
  `Alert` (with `status`) replaces every hand-rolled danger/warning/success banner; `Chip`
  replaces the evaluations-queue count badge and the "Memory off" pill; `Spinner` replaces the
  two inline SVG spinners and the "Loading games..." text; `ProgressBar` replaces the
  hand-rolled context-usage bar; `Table` replaces the scorecard `<table>`.
- **Overlays** — `Modal` replaces the hand-rolled subagent-output overlay and the
  delete-history confirm dialog; the shared `RightDrawer` is reimplemented on Hero UI `Drawer`
  (same props, same `testId`/`ariaLabel`/outside-click-to-close contract), so the evaluations
  queue, scorecard, and Evaluate drawers gain focus trapping and Esc-to-close for free.
- **Tokens** — bespoke colour utilities are replaced by Hero UI status/colour variants where a
  variant exists; `app/globals.css` drops the `label:has(> input[type=…])` cursor rules that
  no longer match anything.

Co-located Vitest specs are updated where Hero UI changes the DOM shape (for example a
Hero UI `Checkbox` root is a `<div>` wrapping a visually-hidden `<input>`, so tests now query
`getByRole("checkbox", { name })` instead of clicking the wrapper's `data-testid`). No
assertion is weakened or removed.

## Non-goals

- No change to data fetching, hooks, routing, API contracts, or any backend service.
- No visual redesign: layout, copy, spacing, and information architecture are unchanged.
- Next.js `<Link>` navigation entries keep using `next/link` (Hero UI `Link` wraps
  `react-aria-components` and would drop Next.js client-side routing and prefetch).
- The per-event "Actions" dropdown keeps its bespoke open/close state (a Hero UI `Popover`
  would change the click-to-select propagation the transcript relies on); only its trigger and
  panel are moved onto `Button` and `Card`.
- `window.confirm` on Play session removal is unchanged; it is a browser affordance, not
  markup.

## Impact

- Affected capability: `dashboard`.
- Affected code: `services/dashboard/app/globals.css` and 23 components under
  `services/dashboard/features/**` plus their co-located `__tests__`.
- No backend, endpoint, or configuration changes.
