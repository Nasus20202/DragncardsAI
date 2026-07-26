## Why

Two dashboard UI patterns were copy-pasted across features:

- A collapsible detail card was defined twice with near-identical markup: `features/play/components/play-event-card.tsx` (`CollapsibleCard`, event-driven, shows a timestamp) and `features/history/components/conversation-transcript.tsx` (`CollapsibleCard`, prop-driven, `data-testid` + `break-words`).
- The right-anchored slide-over drawer shell (dimmed backdrop, outside-click close, full-height `aside` dialog) was repeated three times: `features/history/components/evaluation-queue.tsx`, `features/history/components/history-scorecard.tsx`, and the Evaluate drawer inline in `features/history/components/history-workspace.tsx`.

Consolidating both removes duplication and keeps the shared visual language in one place.

## What Changes

- **dashboard** adds `features/shared/components/collapsible-card.tsx` exporting a single `CollapsibleCard` that reconciles the two prior copies via props (`time`, `defaultOpen`, `breakBody`, `testId`). The Play event card computes label/dot/time and delegates to it; the History transcript imports it directly.
- **dashboard** adds `features/shared/components/right-drawer.tsx` exporting a `RightDrawer` shell (backdrop + outside-click close + right `aside`, parametrized by `ariaLabel`, `testId`, `maxWidthClass`). The evaluations queue, player scorecard, and Evaluate drawer render their header/body as its children.
- Pure internal refactor: no behavior, markup semantics, `data-testid`, `aria` labels, or rendered output change. `useScrollLock` was investigated and found not warranted — the dashboard has no duplicated dynamic body-scroll locking (only a static `overflow-hidden` on `<body>`).

## Impact

- dashboard only; no backend, endpoint, or spec-behavior changes. All drawer/transcript testids, roles, and behaviors are preserved.
