# Adopt OpenUI for the question surface

## Why

DRA-5 shipped the click-to-answer question surface and deliberately did not take
the OpenUI dependency the issue named. Its proposal recorded the evaluation, found
no blocker, and escalated the dependency decision to the owner rather than taking
it. The owner has now ruled: adopt OpenUI.

DRA-5 was built for exactly this. The `ask_user` tool schema, the `job_questions`
table, the server-side answer validation, and the three durable event types were
all designed so that adopting OpenUI replaces **one component** and touches
nothing else. This change does that and no more.

## What the owner's ruling rests on

These were established by the DRA-5 investigation and re-verified against the
published packages before installing anything. If a later change appears to
contradict one of them, that change has left the basis on which adoption was
approved.

- `openui.com` and `github.com/thesysdev/openui` are the **same** project (Thesys
  Inc.). The unrelated `wandb/openui`, which the name also matches, is **not** it.
  Both installed packages declare
  `repository: git+https://github.com/thesysdev/openui.git` and
  `homepage: https://openui.com`, which is what confirms the right project was
  installed.
- **Licence: MIT**, for both packages.
- **A client library, not a hosted service. No Thesys API key and no Thesys
  endpoint.** The parser, the prompt generator, and the renderer all run locally.
  The one networked feature in the API — the `toolProvider` prop, which backs the
  DSL's `Query()`/`Mutation()` calls — is not passed, so nothing in the render
  path talks to anything.

## What is adopted, and what is deliberately not

Two packages, pinned exactly because this is a 0.x library where a caret is a
liability:

| Package | Version | Why |
| --- | --- | --- |
| `@openuidev/react-lang` | 0.2.9 | `defineComponent`, `createLibrary`, `Renderer` |
| `@openuidev/lang-core` | 0.2.10 | the parser and prompt layer it depends on |
| `zod` | 4.4.3 | required peer, used for the component prop schemas |

**`@openuidev/react-ui` is not installed**, and the visual rule is why. It is the
package that would have re-skinned the app: it brings sixteen Radix packages,
`recharts`, `react-syntax-highlighter`, `lucide-react`, `date-fns`, its own
stylesheet — and `react-markdown`, which would put a markdown renderer in the
path of model-authored text. None of that is needed, because OpenUI's
`createLibrary` takes **the adopter's own components**. The question surface is
therefore still built from the same Hero UI primitives and Tailwind theme tokens
it was built from before, and no OpenUI stylesheet is loaded at all.

## What Changes

- **Add three pinned dependencies** to `services/dashboard`:
  `@openuidev/react-lang@0.2.9`, `@openuidev/lang-core@0.2.10`, and their peer
  `zod@4.4.3`.
- **Add `features/play/lib/user-question-lang.ts`**, which builds the OpenUI Lang
  program for a question from that question's shape — the number of choices and
  whether free text is permitted — and interpolates no model-authored string.
- **Add `features/play/lib/user-question-library.tsx`**, the closed component
  library the program is resolved against: `UserQuestion`, `QuestionPrompt`,
  `ChoiceList`, `Choice`, `FreeTextAnswer`. Each is built from the Hero UI
  primitives and Tailwind tokens the DRA-5 card already used, each re-checks its
  own props against the stored question, and the stored question reaches them
  through a React context rather than through the program.
- **Rewrite `features/play/components/user-question-card.tsx`** to render that
  program inside the existing card frame. It keeps the card's lifecycle states
  (answered, closed, terminal, submit error) and the double-submit guard, and it
  remains the only place an answer is submitted from — resolving a choice's index
  against its own `question` prop.
- **Add `features/play/__tests__/user-question-openui.test.tsx`**, which drives
  hostile programs — forged indices, excess arguments, undefined components, an
  unpermitted free-text box, injected markup — against the real library.
- **Add one orchestrator test** asserting ten forged `choice_value` submissions are
  each refused with the question left pending.
- **Document the dependency** in `services/dashboard/AGENTS.md`: the MIT licence,
  the "no key, no endpoint" fact, why `@openuidev/react-ui` is excluded, the
  `wandb/openui` name collision, and the four rules a change here must not break.
- **Change nothing else.** The `ask_user` tool schema, the `job_questions` table,
  the answer endpoint's validation, the three durable event types, and every other
  dashboard component are untouched.

## The security boundary does not move

OpenUI's premise is that a model authors UI in a DSL, which is a materially larger
rendering surface than a validated list of choices. The boundary is held in four
places, each with a test:

1. **The server is still the authority.** A submitted `choice_value` is checked
   against `choices_json` read back from the row, and `answer_label` is derived
   from stored state. Unchanged by this change, and now covered by a test that
   walks ten forged values — a label submitted in place of its value, a
   description, case and whitespace variants of a real value, positional guesses
   — and asserts each is refused with the question left pending.
2. **No model-authored text is interpolated into DSL source.** This is the new
   sink the DSL introduces, and the reason the generator takes no strings.
   OpenUI Lang has double-quoted string literals, so a label containing `"` ends
   one and the remainder parses as code; this was confirmed against the parser,
   where `Text("with "quotes"")` yields three arguments and an `excess-args`
   error. The emitted program is built from the question's *shape* — how many
   choices, whether free text is permitted — so it contains component names and
   integers and nothing else.
3. **A choice is addressed by index, never by value.** `Choice` takes its
   position in the stored choice list and has no other prop, so the DSL has no
   syntax for a label or a value. A program can reorder or omit choices, which is
   presentation; it cannot invent one, relabel one, or name one the row does not
   contain.
4. **A prop schema is not a runtime guard.** Worth stating because it is the
   assumption most likely to be made wrongly later: the zod schemas generate the
   model's prompt and produce validation errors, but the parser renders
   permissively. `Choice("not-a-number")` reaches the renderer with the string
   intact, and `Choice(99)` reaches it with an index no choice occupies. Every
   renderer therefore re-checks its own props against the stored question and
   renders nothing when they do not hold.

A fifth property comes free from the library rather than from this change: a
library is a **closed registry**, so a program naming a component that was never
defined renders nothing and is reported as `unknown-component`. There is no
escape hatch to raw markup.

## Impact

- `services/dashboard` — one component replaced, two modules added, three
  dependencies added. No other component changed, and nothing restyled.
- `services/agent-orchestrator` — one test added. No source change.
- The `ask_user` schema, the `job_questions` persistence, the answer endpoint, and
  the three durable event types are untouched, which is what let this change stay
  this small.

## Not done here

**DRA-22's tool-call renderer registry is left on Hero UI.** It was built so a
richer library is a localised swap, and moving it to OpenUI is a reasonable
follow-up — but it is a separate surface with its own bounded-output and
secret-redaction rules, and folding it in would have made this change about two
things. It is not required by DRA-29 and is not started.
