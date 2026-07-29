# Dashboard Service Agent Guide

Read this file before making changes in `services/dashboard/`.

## Scope

These instructions apply to the dashboard service and override the repository-level `AGENTS.md`.

## Tech Stack

- **Framework**: Next.js 16 with React 19
- **UI Library**: Hero UI (`@heroui/react`, `@heroui/styles` v3.2.2 — the **v3** API)
- **Generative UI**: OpenUI Lang (`@openuidev/react-lang`) — the `ask_user` question
  surface only. See [Generative UI (OpenUI)](#generative-ui-openui).
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

### Per-Service Lists

`features/proxy/lib/proxy.ts` declares `SERVICE_KEYS` once — the first-party services the
dashboard fronts — and derives `ServiceKey` from it. The `/api/proxy/[service]` route, the
upstream base-URL lookup (`getServiceBaseUrl`), the OpenAPI path prefix
(`getServiceProxyPrefix`), and the merged Swagger index in `features/swagger/lib/openapi.ts`
all key off that one declaration.

Anything per-service is a `Record<ServiceKey, …>` or a loop over `SERVICE_KEYS`, never a
literal list of names and never a branch chain that falls through to a default service — both
of those let a service be half-added. That is exactly how history-service and eval-service
ended up proxyable but missing from `/swagger` (DRA-20). A service's base URL and OpenAPI path
come from `features/config/lib/dashboard-config.ts`, and every variable that file reads must
also be listed in `vitest.setup.ts`.

### Generative UI (OpenUI)

The question surface the `ask_user` tool produces renders through **OpenUI Lang**,
a DSL in which a model can author UI. Only that surface uses it; every other part
of the dashboard is Hero UI plus Tailwind as described above.

**Why this dependency was acceptable** — check these still hold before upgrading it:

- **Licence: MIT**, for every package used.
- **No API key and no endpoint.** OpenUI is a client library, not a hosted
  service. Nothing in the render path talks to Thesys or anywhere else: the
  parser and renderer are local, and the one networked feature (`toolProvider`,
  for the DSL's `Query()`/`Mutation()`) is not passed. If a change appears to
  need a key or an endpoint, stop — that is not the basis on which this
  dependency was accepted.
- **Only the two `lang` packages are installed**, pinned exactly (no `^`: it is a
  0.x library): `@openuidev/react-lang` and `@openuidev/lang-core`, plus `zod`
  as their peer. `@openuidev/react-ui` is deliberately **not** installed — it
  ships Radix, recharts, `react-markdown` and its own theme, which would re-skin
  the app and add a markdown sink for model-authored text.
- **Do not confuse the projects.** `openui.com` / `github.com/thesysdev/openui`
  (Thesys Inc.) is this one. The unrelated `wandb/openui` is not.

**Where it lives:**

- `features/play/lib/user-question-library.tsx` — the component library. This is
  a **closed registry**: a program naming a component absent from this file
  renders nothing.
- `features/play/lib/user-question-lang.ts` — builds the program for a question.
- `features/play/components/user-question-card.tsx` — the card frame, and the
  only place an answer is submitted from.

**Four rules a change here must not break.** They are what keeps a DSL from being
a wider hole than the list of buttons it replaced, and each has a test in
`features/play/__tests__/user-question-openui.test.tsx`:

1. **Never interpolate model-authored text into DSL source.** OpenUI Lang has
   double-quoted string literals, so a label containing `"` breaks out of one and
   the remainder parses as code — the same class of sink as
   `dangerouslySetInnerHTML`. `buildUserQuestionLang` emits component names and
   integers only; every string is looked up at render time.
2. **A prop schema is not a runtime guard.** The zod schemas generate the model's
   prompt and produce validation errors, but the parser renders permissively —
   `Choice("not-a-number")` reaches the renderer with the string intact. Every
   renderer re-checks its own props.
3. **Address stored data by index, never by value.** A `Choice` carries its
   position in the stored choice list and nothing else, so no program can invent,
   relabel, or rename a choice. The value submitted is read from the row.
4. **Model-authored strings are rendered as plain React text children.** No
   `dangerouslySetInnerHTML`, no markdown renderer, no browser-resolved attribute
   (`href`, `src`, `style`, `on*`).

None of this replaces server-side validation, which is the real boundary: the
orchestrator checks a submitted `choice_value` against `choices_json` read back
from the question's row and derives `answer_label` from stored state, so a forged
value is refused whatever was rendered.

## The Service Proxy

`app/api/proxy/[service]/[...path]/route.ts` is the single route every browser call
to agent-orchestrator, game-service, history-service, and eval-service goes
through. It is a **pass-through**, and the bodies it carries are large: a lossless
history export of a real game is tens of megabytes, and the import endpoint it
feeds validates line by line.

Rules it must keep:

- **Never read a body.** The request body goes out as `request.body` (via
  `buildProxyRequestInit`) and the response comes back as `upstreamResponse.body`.
  `await request.arrayBuffer()`, `await upstreamResponse.json()`, or any other read
  makes the whole payload resident in this process and defeats an upstream that
  streams. A `ReadableStream` body also requires `duplex: "half"` on the outbound
  `fetch` — Node throws without it.
- **The proxy has no size cap, deliberately.** Each service enforces its own, and
  they differ on purpose (the orchestrator's `MAX_REQUEST_BODY_BYTES` is 8 MiB,
  history's `HISTORY_IMPORT_MAX_BYTES` is 64 MiB). Adding one here would pick a
  single number for four services. Do forward a declared `Content-Length` so those
  services can still refuse an oversized upload before reading it.
- **Keep the header filters doing their job.** `filterProxyRequestHeaders` drops
  the hop-by-hop set — `transfer-encoding` above all, which Node's `fetch` refuses
  to send and which is the header a request-smuggling attempt needs — plus the
  browser's `cookie`/`authorization` and all `x-forwarded-*`.
  `filterProxyResponseHeaders` drops the upstream's framing headers while keeping
  `content-disposition` so downloads keep their filename.
- **Keep the request checks ahead of the forward.** Cross-site rejection, the
  service-name check, and `assertSafeSegment` all run before any upstream
  connection, so a rejected request sends no bytes anywhere.

`features/proxy/__tests__/proxy-route.test.ts` exercises the route against a real
loopback server on an ephemeral port, because whether a body streams is a wire
property no stubbed `fetch` can show. Add to it rather than mocking `fetch`.

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
