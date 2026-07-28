# The agent asks a question and the user answers it by clicking

## Why

Every question the agent asks today arrives as prose in the transcript and has to
be answered as prose in the composer. The reporter of DRA-5 wants the other
thing, in their words: *"whenever we are asked something by the model we should
be able to easily click on the buttons / forms elements to answer it's questions
(a bit like ask_user in claude code)."*

Two costs come out of the typed-prose status quo. The obvious one is friction —
"which hero should I play?" takes a sentence to answer instead of a click. The
less obvious and more damaging one is that a prose question has no identity: the
run does not know it asked, does not know whether it was answered, and cannot
constrain the answer. So the model either guesses and proceeds, or it ends the
turn and asks the user to start a new one, losing the run's context in between.
A question the run *waits on* is a different mechanism from a question it merely
prints, and only the former can be answered by clicking.

## The OpenUI evaluation, and why it is not adopted here

The issue names OpenUI as the way to do this. It was evaluated, because the name
is ambiguous and the reporter's two links needed to be checked against each
other. Findings, with evidence:

- The two links are the **same** project. `https://www.openui.com/` is the
  marketing site for `https://github.com/thesysdev/openui`, run by **Thesys
  Inc.** (San Francisco). This matters because an unrelated `wandb/openui`
  exists — a prompt-to-UI playground — and it is *not* what was linked.
- **Licence: MIT**, `Copyright (c) 2011-2024 Thesys Inc.` The licence is not an
  obstacle.
- It is a **client library, not a hosted service**, for the part that is open
  source. It publishes nine npm packages (`@openuidev/lang-core`,
  `@openuidev/react-lang`, `@openuidev/react-headless`, `@openuidev/react-ui`,
  `@openuidev/react-email`, `@openuidev/vue-lang`, `@openuidev/svelte-lang`,
  `@openuidev/browser-bundle`, `@openuidev/cli`).
- **No Thesys API key and no Thesys endpoint is required** by those packages.
  The only key in the quick start is the adopter's own `OPENAI_API_KEY`, used to
  call the adopter's own model provider. `@openuidev/react-lang@0.2.9` depends
  only on `@openuidev/lang-core`, with `react`, `zod`, and an optional
  `@modelcontextprotocol/sdk` as peers. **So adopting the OSS packages would not,
  by itself, send chat content or game state to a third party.**
- It is **actively maintained** — 8.2k stars, ~719 commits on `main`, and
  `@openuidev/react-lang` last published 2026-07-24.
- There is also a commercial **"OpenUI Cloud"** (pre-tested components, design
  tokens, provider resilience, demo-call pricing). That tier is a hosted service
  and would involve Thesys-side processing. Nothing forces us onto it.

So there is no licence, key, or data-egress blocker. The reason not to adopt it
in this change is a fit-and-cost reason instead:

1. **It solves a much larger problem than the one reported.** OpenUI's premise is
   that the model authors arbitrary UI in a DSL ("OpenUI Lang") which the client
   renders. DRA-5 needs a question with a fixed set of choices. Taking the
   framework means accepting model-authored UI as a rendering surface inside the
   dashboard — a materially larger attack surface than validating a choice list,
   for a capability we did not ask for.
2. **It would collide with the dashboard's visual reference.** The value in
   `@openuidev/react-ui` is its own component set and chat layout. The dashboard
   is Hero UI v3 with a hand-rolled transcript, and the standing rule is that
   existing components are not restyled. We would be importing a component
   library in order to not use most of it.
3. **It is pre-1.0 and moving fast** (`0.2.9`, nine packages, a DSL that is
   itself the product). That is a reasonable bet for a UI-generation product and a
   poor one for a narrow question widget.

**This is a recommendation, not a decision.** Adding a third-party runtime
dependency is the repository owner's call, and it is escalated to them
unresolved. What this change does is make the escalation cheap either way: the
question is defined as a *typed contract* (a tool schema, three job event types,
one answer endpoint) and the rendering is one isolated component behind that
contract. Adopting OpenUI later means replacing that one component, with the
tool, the persistence, the validation, and the event stream untouched.

## What Changes

- **agent-orchestrator (new built-in tool)** — an `ask_user` tool joins the
  built-in registry alongside `spawn_subagent` and `wait_for_subagent`, gated to
  top-level jobs. The model calls it with a question and between one and eight
  labelled choices, and optionally permits a free-text answer. The tool blocks
  until the user answers or the wait is closed, then returns the answer as an
  ordinary tool result. No side channel: the answer re-enters the model's context
  through the same `role: "tool"` message every other tool result uses.
- **agent-orchestrator (persistence)** — a new `job_questions` table holds the
  question, the exact choices offered, and the answer. Postgres, not memory: the
  worker that asked and the HTTP request that answers are different processes and
  may be different replicas, and a pending question has to survive both a page
  reload and a reconnect.
- **agent-orchestrator (new endpoint)** — `POST
  /jobs/{job_id}/questions/{question_id}/answer` records an answer. It validates
  the submitted choice against the choices stored server-side, so the client
  cannot answer with something that was never offered and cannot widen what the
  model asked for.
- **agent-orchestrator (events)** — three non-terminal job events —
  `user_question`, `user_question_answered`, `user_question_closed` — are
  persisted and published, so the transcript shows the question, its answer, and
  a question that stopped awaiting one.
- **agent-orchestrator (configuration)** — `ask_user_timeout_seconds` and
  `ask_user_poll_interval_seconds` bound how long a run waits on a human and how
  often it re-reads the answer, following the existing `subagent_wait_*` pattern.
- **dashboard (new component)** — a question card in the transcript renders the
  question and one Hero UI button per choice, plus a free-text field when the
  model allowed one. Clicking a button answers the question. The card also
  renders the answered and closed states, so a reload shows what happened rather
  than live buttons for a question that is over.
- **dashboard (event handling)** — the three new event types are registered on
  the SSE stream and aggregated so the answered and closed events resolve the
  question row instead of appearing as rows of their own.

## Capabilities

### Modified Capabilities

- `agent-orchestrator` — gains the ask-the-user tool, the pending-question store,
  the answer endpoint, and the three question events.
- `dashboard` — gains the in-transcript question surface and its event wiring.

## Impact

- **Production code** — `runtime/builtin_tools.py` (the tool and its wait),
  `runtime/prompt_run.py` (registry wiring), `storage/models.py`, a new
  `repositories/questions.py` mixin, `api/routers/jobs.py`, `schemas/jobs.py`,
  `config.py`; dashboard `features/play/` (a new component, the event model, the
  API client, the action hook).
- **Database** — one new table, `job_questions`, added by migration `0009` in both
  the PostgreSQL and SQLite dialects.
- **Tests** — orchestrator unit tests for the tool's schema and gating, the
  server-side validation of a submitted answer against the offered choices, the
  double-answer race, the timeout path, and the job-terminal path; dashboard tests
  for the clickable question, the reload case, the double answer, and the literal
  rendering of model-authored text.
- **Documentation** — the agent-orchestrator README's built-in tool list and event
  list, and the two new settings in its configuration section.

## Non-goals

- **No OpenUI dependency in this change.** The evaluation above is the
  deliverable; the dependency itself is the owner's decision and is escalated.
- No model-authored UI beyond a question and a list of choices. The model chooses
  *what to ask*, never *what to render*.
- No multi-select, no nested or dependent questions, no file or image answers. One
  question, one answer.
- No suspend-and-resume of a job. The run waits inside the tool call, which is the
  idiom `wait_for_subagent` already established; a question outliving its worker
  is handled by closing it, not by resurrecting the run.
- No question that blocks forever. The wait is bounded, and an unanswered question
  returns a result the model can act on rather than hanging the session.
- No restyling of the existing transcript, composer, or tool-call rendering. The
  question card is new; everything around it is untouched.
- No queue of several questions at once. A run asks one question at a time because
  it is blocked while it asks.
