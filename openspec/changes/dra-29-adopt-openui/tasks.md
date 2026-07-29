# Tasks

## 1. Verify the facts adoption was approved on

- [x] 1.1 Confirm the installed packages are Thesys's OpenUI and not `wandb/openui`,
      by reading `repository` and `homepage` off the published package metadata.
- [x] 1.2 Confirm the licence is MIT for both packages.
- [x] 1.3 Confirm no Thesys API key and no Thesys endpoint is required: read the
      whole exported API surface of `@openuidev/react-lang` and check that the only
      networked feature, the `toolProvider` prop, is optional and unused.
- [x] 1.4 Confirm `@modelcontextprotocol/sdk` is an *optional* peer, so it does not
      have to be installed.

## 2. Choose the smallest package set that does not re-skin the app

- [x] 2.1 Read `@openuidev/react-ui`'s dependency list and reject it: sixteen Radix
      packages, `recharts`, `lucide-react`, its own stylesheet, and `react-markdown`
      in the path of model-authored text.
- [x] 2.2 Confirm `createLibrary` accepts the adopter's own components, so the
      existing Hero UI renderers can be kept.
- [x] 2.3 Install `@openuidev/react-lang@0.2.9`, `@openuidev/lang-core@0.2.10` and
      `zod@4.4.3`, pinned exactly with `--save-exact`.
- [x] 2.4 Confirm `pnpm peers check` reports no new unmet peer for the added
      packages.

## 3. Learn the DSL's actual behaviour before designing against it

- [x] 3.1 Establish the statement syntax, positional arguments, hoisting, and how
      children are declared (`Choice.ref`) and rendered (`renderNode`).
- [x] 3.2 Establish that renderers receive `{ props, renderNode }` rather than
      spread props, correcting the README's example.
- [x] 3.3 Establish that an unknown component renders nothing and is reported as
      `unknown-component`.
- [x] 3.4 Establish that the zod prop schemas are **not** enforced at render time:
      confirm `Choice(99)`, `Choice(-1)`, `Choice(1.5)` and `Choice("she-hulk")` all
      reach the renderer.
- [x] 3.5 Establish that an unescaped `"` in a string literal breaks out of it,
      making string interpolation into DSL source an injection sink.

## 4. Build the question surface on OpenUI

- [x] 4.1 Add `features/play/lib/user-question-lang.ts`, building the program from
      the question's shape only, with no string interpolation.
- [x] 4.2 Add `features/play/lib/user-question-library.tsx`: `UserQuestion`,
      `QuestionPrompt`, `ChoiceList`, `Choice`, `FreeTextAnswer`, built from the
      same Hero UI primitives and Tailwind tokens the DRA-5 card used.
- [x] 4.3 Give every renderer its own prop re-check, since the schema is not a
      runtime guard: integer-and-in-bounds for `Choice`, stored `allowFreeText` for
      `FreeTextAnswer`.
- [x] 4.4 Carry the stored question to the renderers through `QuestionContext`, and
      keep the submit callback taking an index so no renderer ever holds a value.
- [x] 4.5 Rewrite `features/play/components/user-question-card.tsx` to render the
      program, resolving the index against its own `question` prop when submitting.
- [x] 4.6 Emit controls into the program only while the question is pending, so a
      resolved question cannot render a button.

## 5. Prove the boundary held

- [x] 5.1 Keep all eight DRA-5 transcript tests passing **unchanged**, including the
      one asserting `<img src=x onerror=…>` stays literal text.
- [x] 5.2 Add `features/play/__tests__/user-question-openui.test.tsx` covering: the
      program carries no model-authored text; a forged or malformed index renders
      nothing; excess arguments cannot relabel a choice; an unknown component
      renders nothing; a free-text box is refused unless the row permits one;
      model-authored strings stay literal through the OpenUI renderer.
- [x] 5.3 Add an orchestrator test walking ten forged `choice_value` submissions —
      a label for its value, a description, case and whitespace variants,
      positional guesses — asserting each is refused and the question left pending.
- [x] 5.4 Mutation-test the three new dashboard guards and the server's choice
      check, confirming each test fails when its guard is removed.

## 6. Confirm the look is unchanged

- [x] 6.1 Diff the rendered DOM against the DRA-5 structure; find that
      `span.contents` wrappers collapse `space-y-2.5`, and fix by rendering children
      as keyed `Fragment`s.
- [x] 6.2 Drive the surface in a real browser across all six states (pending with
      and without free text, answered, closed, terminal job, injection attempt) and
      confirm the spacing measures 10px and no OpenUI stylesheet is loaded.
- [x] 6.3 Confirm in the browser that clicking an OpenUI-rendered choice submits the
      **stored** value (`she-hulk`) and that free text submits trimmed, through real
      Hero UI and react-aria rather than the test mocks.
- [x] 6.4 Confirm the injected `<script>`, `<img>` and `<b>` strings appear as
      literal text with no corresponding elements in the live DOM.

## 7. Record why the dependency was acceptable

- [x] 7.1 Add a "Generative UI (OpenUI)" section to `services/dashboard/AGENTS.md`
      recording the MIT licence, the "no key, no endpoint" fact, why
      `@openuidev/react-ui` is excluded, the `wandb/openui` name collision, and the
      four rules a change must not break.
- [x] 7.2 Add OpenUI to that file's Tech Stack list, scoped to the question surface.

## 8. Checks

- [x] 8.1 `./scripts/lint.sh --fix`
- [x] 8.2 `pnpm typecheck` in `services/dashboard`
- [x] 8.3 `./scripts/test.sh unit`
- [x] 8.4 `openspec validate --all`
