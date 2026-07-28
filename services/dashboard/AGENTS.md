# Dashboard Service Agent Guide

Read this file before making changes in `services/dashboard/`.

## Scope

These instructions apply to the dashboard service and override the repository-level `AGENTS.md`.

## Tech Stack

- **Framework**: Next.js 16 with React 19
- **UI Library**: Hero UI (`@heroui/react`, `@heroui/styles` v3.2.2 — the **v3** API)
- **Styling**: Tailwind CSS 4 with Hero UI preset
- **TypeScript**: Strict mode enabled
- **Testing**: Vitest with React Testing Library

## Project Structure

```
features/
  games/           # Game session management
    components/    # GamesSessionList, DragnCardsIframe, GamesWorkspace
    lib/           # useGames hook
  shared/          # Shared types and utilities
```

## Component Guidelines

### Hero UI Components

Always use Hero UI components from `@heroui/react` instead of native HTML elements. Import directly:

```tsx
import { Button, Card, Chip, Spinner, Input, Modal } from "@heroui/react";
```

Common component mappings:

- Buttons: `Button` (not `<button>`) — variants in use are `primary`, `ghost`, `danger`, `danger-soft`
- Cards: `Card` for containers
- Form inputs: `TextField` wrapping `Input`, `TextArea`, `Select`, `ComboBox`
- Layout: `Separator`
- Loading: `Spinner`
- Badges: `Chip` (always `size="sm" variant="soft"`)
- Modals: `Modal`, `ModalHeader`, `ModalHeading`, `ModalBody`, `ModalFooter`, `ModalCloseTrigger`

This is the **v3** API, so use `onPress` (not `onClick`) and `isDisabled` (not `disabled`) on Hero UI
components. `CardBody`, `ModalContent`, `Textarea`, `RadioGroup`, and `Checkbox` are v2 names and are
not available — check what the code already imports before reaching for a component.

Hero UI belongs to the _chrome_ (composer, dialogs, panels, config drawers). The chat transcript is
deliberately hand-rolled `div`/`button` plus Tailwind theme tokens: match the surrounding blocks there
rather than converting them, and never restyle an existing component.

### Styling

Use Hero UI's theme classes:

- Colors: `text-default-500`, `text-danger`, `bg-background`, `border-default-200`
- Spacing: Standard Tailwind (`p-4`, `gap-3`, `flex-1`)
- Responsive: Use Hero UI's responsive utilities

Example:

```tsx
<Card className="p-4 shadow-none">
  <h2 className="text-lg font-semibold">Title</h2>
  <p className="text-sm text-default-500">Description</p>
</Card>
```

### Transcript Tool Cards

The Play transcript renders each tool invocation through a registry, so giving a
system tool its own card is an entry in a table rather than a new special case:

- `features/play/lib/tool-call-presentation.ts` holds `TOOL_PRESENTATIONS`
  (tool name → presentation key) plus the bounded, redacting formatters every card
  uses.
- `features/play/components/tool-exchange-block.tsx` holds `RENDERERS`
  (presentation key → renderer) and falls back to the generic card for any tool
  absent from the table.

To add a bespoke card: add the tool name to `TOOL_PRESENTATIONS`, add a renderer
to `RENDERERS` under the same key, and build it from the shared `ToolCard` frame
so it keeps the transcript's look. Two rules a renderer must not break:

- A **collapsed** card may only use the bounded helpers (`buildToolExchangeView`,
  `boundedValueText`, `boundedResultText`). Never serialise a whole payload
  outside an expanded body — a tool result can carry a full board state.
- Everything displayed is text and goes through `redactSecrets`. Tool arguments
  are model-supplied and results are server-supplied.

## Working Rules

- Use Hero UI components for all interactive elements
- Follow the existing component structure (client components with "use client")
- Place new components in `features/<feature>/components/`
- Place hooks in `features/<feature>/lib/`
- Use TypeScript strict mode - no `any` types
- Prefer `className` over inline styles for consistency

## Testing

```bash
pnpm test              # Run vitest
pnpm test -- --ui     # Run with UI
```

Tests live alongside components in `__tests__/` directories.

## Commands

```bash
pnpm dev              # Start dev server
pnpm build            # Build for production
pnpm lint             # Run ESLint
pnpm typecheck        # Run TypeScript compiler
pnpm format           # Format with Prettier
pnpm format:check     # Check formatting
```

## Agent Guidance

1. Before creating new components, check existing Hero UI patterns in `features/`
2. Follow the "use client" directive for interactive components
3. Use Hero UI's TypeScript types - they are included in the package
4. When styling, prefer Hero UI theme tokens over custom values
