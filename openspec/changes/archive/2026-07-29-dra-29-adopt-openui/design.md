# Design

## The shape of the problem

OpenUI's model is: the adopter defines a component library with zod prop schemas,
OpenUI generates a system prompt describing it, the model emits a program in
OpenUI Lang, and `Renderer` parses that program and renders it against the
library. A program looks like this:

```
root = UserQuestion([prompt, choices])
prompt = QuestionPrompt()
choices = ChoiceList([choice0, choice1])
choice0 = Choice(0)
choice1 = Choice(1)
```

Statements are `identifier = Component(positional, args)`, references may be
hoisted, and unreferenced statements are dropped.

The question this change had to answer is how model-authored data reaches that
program, because DRA-29 keeps the `ask_user` tool schema. The model does not
author the program today — it supplies a question and a list of choices, which the
orchestrator validates and stores. So the dashboard synthesises the program from
the stored row.

## Why the generator takes no strings

The obvious synthesis is to interpolate the stored question and labels into the
source:

```
prompt = QuestionPrompt("Which hero should I play?")
choice0 = Choice("spider-man", "Spider-Man")
```

That is a code-injection sink, and it is the one genuinely new risk the DSL
introduces. OpenUI Lang string literals are double-quoted with backslash escaping,
so a model-authored label containing `"` terminates the literal and everything
after it parses as further arguments — or further statements. Verified against
`@openuidev/lang-core` 0.2.10: `Text("with "quotes"")` parses as three arguments
and reports `excess-args`, with the label truncated to `with `. It is the same
class of mistake as building HTML by concatenation, and escaping is the fix that
looks sufficient and is one bug away from not being.

So the generator does not interpolate at all. `buildUserQuestionLang` reads two
facts off the stored question — `choices.length` and `allowFreeText` — and emits a
program whose only variable content is an integer index. Every string is looked up
at render time, from the stored prompt, by the component that displays it. The
emitted program contains no `"` character, which is a property a test asserts
directly rather than inferring.

This has a consequence worth naming, because it is the reason the design is
defensible under the follow-up everybody will want: **if the model is later given
the pen** and authors the program itself, the boundary survives unchanged.
Whatever program it writes, `Choice` still takes an index into the stored list, so
it still cannot name a choice the row does not contain.

## Why every renderer re-checks its props

The natural reading of `defineComponent({ props: z.object({ index: z.number().int() }) })`
is that the renderer receives a validated integer. It does not. The schemas drive
prompt generation and produce `ParseResult.meta.errors`, but the parser is
documented as permissive — "errors do not affect rendering" — and it is. Feeding
the real library a hostile program:

```
a = Choice(99)            → renderer receives index 99
b = Choice(-1)            → renderer receives index -1
c = Choice(1.5)           → renderer receives index 1.5
d = Choice("she-hulk")    → renderer receives index "she-hulk"
e = Evil("<img src=x …>") → dropped, unknown-component
```

Only the unknown component is stopped by the library. The four malformed indices
all arrive. So `ChoiceView` checks `Number.isInteger` and the array bounds itself,
and returns `null` otherwise — which is safe by construction, because an index
that addresses no stored choice has no label to show and no value to submit.

`FreeTextAnswerView` does the same against the stored `allowFreeText` rather than
against the program: a program asking for a text box on a question that does not
permit free text gets nothing, so the surface never invites an answer the
orchestrator would refuse.

## How the stored question reaches the renderers

`Renderer` gives a component only the props its program supplied, so the stored
question has to arrive out of band. A React context (`QuestionContext`) carries
the prompt, the answerability flags, and the two submit callbacks; the card
provides it, and the renderers consume it.

The submit path is deliberately narrow. `ChoiceView` calls
`onSubmitChoice(index)` — it never sees a value. The card resolves the index
against its own `question` prop and sends `{ choice_value: choices[index].value }`.
So the value on the wire comes from the card's props, never from the rendered
program, and a renderer has nothing it could substitute.

## Keeping the look identical

Two decisions:

- **`@openuidev/react-ui` is not installed.** `createLibrary` takes the adopter's
  own components, so the renderers are the same Hero UI `Button`, `TextField` and
  `Input` with the same Tailwind classes the DRA-5 card used. Verified in a
  browser: no stylesheet whose href matches `openui` is loaded.
- **Children render as `Fragment`, not as a wrapper element.** The first version
  wrapped each child in `<span className="contents">` to carry the React key. That
  is a real bug and it was caught by inspecting the rendered DOM rather than by a
  test: Tailwind's `space-y-2.5` spaces siblings with `margin-top` on the direct
  children, and margins on a `display: contents` element are ignored, so every
  vertical gap in the question surface collapsed to zero. A keyed `Fragment`
  creates no DOM node, so the question text and the controls stay the direct
  children of `space-y-2.5`. Measured in the browser afterwards: 10px, which is
  `space-y-2.5`.

What OpenUI does add to the DOM is two wrapper `div`s of its own, carrying
`position: relative` and a 0.2s opacity transition. They are inline styles on the
question surface only, they introduce no classes, and they do not affect layout.

## Alternatives rejected

- **Interpolate strings, with escaping.** Rejected above: it makes correctness
  depend on an escaper, when passing no strings at all removes the sink.
- **Pass the labels through `initialState` as `$`-prefixed reactive variables.**
  This keeps them out of the source text, which is the right instinct, but it
  needs one variable per choice and puts the values in the renderer's reach again
  for no benefit over an index.
- **Install `@openuidev/react-ui` and use its components.** Rejected on the visual
  rule and on the `react-markdown` sink.
- **Render the answered and closed states through OpenUI too.** They are a single
  line of text each and are lifecycle notices rather than a question, so they stay
  plain React in the card. The program simply omits every control once the
  question is no longer pending, which also means a resolved question cannot
  render a button.
