# Tasks

## 1. Establish what OpenUI is before committing to it

- [x] 1.1 Check whether `https://www.openui.com/` and
      `https://github.com/thesysdev/openui` are the same project, and rule out the
      unrelated `wandb/openui` the name also matches.
- [x] 1.2 Record the licence, the published packages, and whether the runtime needs
      a Thesys API key or a Thesys endpoint — that is, whether adopting it would
      send chat content or game state to a third party.
- [x] 1.3 Record maintenance signals (stars, commit count, last publish date) and
      the existence of the paid "OpenUI Cloud" tier.
- [x] 1.4 Write the recommendation and the evidence into `proposal.md`, and state
      that the dependency decision is escalated to the owner rather than taken
      here.

## 2. Confirm the existing paths before changing them

- [x] 2.1 Confirm a job cannot suspend: `PromptRunService.run` is a bounded tool-round
      loop over a local, unpersisted `messages` list, and no job status or re-entry
      point exists for a waiting run.
- [x] 2.2 Confirm `wait_for_subagent` / `resolve_child_outcome` is the established
      idiom for a tool that waits on something external, and that
      `WorkerService.run_forever` detaches each job so a blocked handler does not
      stall the claim loop.
- [x] 2.3 Confirm event types are bare strings with no enum, that
      `TERMINAL_EVENT_TYPES` closes the SSE stream, and that a new event type
      therefore needs no migration but does need registering in the dashboard's
      `STREAM_EVENT_TYPES`.
- [x] 2.4 Confirm the migration mechanism is hand-numbered dual-dialect raw SQL with
      no Alembic, so `0009` must be written for both PostgreSQL and SQLite.

## 3. Orchestrator: store the question

- [x] 3.1 Add the `JobQuestion` model to `storage/models.py` with the question, the
      offered choices, the free-text flag, the status, and the recorded answer,
      cascading from both the job and the session.
- [x] 3.2 Add migration `0010_job_questions` (renumbered from `0009` on merge: DRA-16 landed its own `0009_agent_personas` first) in the PostgreSQL and SQLite dialects.
- [x] 3.3 Add a `QuestionRepositoryMixin` with a create, a read, and the two
      conditional transitions, each applied with `WHERE status = 'pending'` so the
      row count decides who won.
- [x] 3.4 Compose the mixin into `Repository`.
- [x] 3.5 Add unit tests for the conditional transitions, including two answers
      racing for the same question.

## 4. Orchestrator: the ask_user tool

- [x] 4.1 Add `ask_user` to `builtin_tools.py` — argument validation, the recorded
      question, the `user_question` event pair, and the bounded wait that re-reads
      the stored row.
- [x] 4.2 Close the question before returning on timeout or cancellation, publishing
      `user_question_closed`, and return a non-error result for a timeout so the
      model does not retry it as a transient failure.
- [x] 4.3 Register the tool in `build_builtin_registry`, gated to master jobs, and
      thread the two new settings through from `prompt_run`.
- [x] 4.4 Add `ask_user_timeout_seconds` and `ask_user_poll_interval_seconds` to
      `config.py` with positive-value validators.
- [x] 4.5 Add unit tests: schema and gating, argument rejection, the answered path
      returning the answer, the timeout path closing the question, and the
      cancellation path.

## 5. Orchestrator: the answer endpoint

- [x] 5.1 Add the request and response schemas to `schemas/jobs.py`.
- [x] 5.2 Add `POST /jobs/{job_id}/questions/{question_id}/answer` to
      `api/routers/jobs.py`, validating the submitted choice against the stored
      choices, refusing free text the question did not permit, refusing a
      question that is no longer pending, and refusing a question whose job has
      reached a terminal status.
- [x] 5.3 Append and publish `user_question_answered` on success.
- [x] 5.4 Add unit tests: a valid choice, a value that was never offered, free text
      when not permitted, both forms at once, neither form, the double answer, and
      the terminal-job case.

## 6. Dashboard: the question surface

- [x] 6.1 Register the three event types in `STREAM_EVENT_TYPES` and give the
      question its own aggregated kind, so the answered and closed events resolve
      the question row instead of becoming rows of their own.
- [x] 6.2 Add the `UserQuestionCard` component rendering the pending, answered,
      closed, and unanswerable states in the transcript's existing visual language.
- [x] 6.3 Render all model-authored strings as plain text children only — no
      markdown, no markup, no attribute interpolation.
- [x] 6.4 Add `answerUserQuestion` to `client-api.ts` and wire the submit path
      through the play-session action hook.
- [x] 6.5 Add tests: clicking a choice submits it, a replayed answered timeline shows
      the answer with no controls, a second click while submitting sends nothing and
      a refusal leaves the controls disabled, a closed question renders closed, and
      a label containing markup stays literal text.

## 7. Keep the surrounding files current

- [x] 7.1 Document `ask_user` in the agent-orchestrator README's built-in tool list,
      including that it blocks and that the wait is bounded.
- [x] 7.2 Add the three new event types to the README's job event list and to the
      list in `services/agent-orchestrator/AGENTS.md`.
- [x] 7.3 Document the two new settings in the README's configuration section.
- [x] 7.4 Confirm no `.env.example`, `docker-compose.yaml`, Dockerfile, or script
      change is needed, and say so — the two new settings have working defaults and
      no third-party dependency was added, so there is no credential or endpoint to
      introduce.

## 8. Verification

- [x] 8.1 `./scripts/lint.sh --fix` clean.
- [x] 8.2 `./scripts/test.sh unit` passes, with the orchestrator and dashboard counts
      recorded before and after.
- [x] 8.3 `pnpm typecheck` clean in `services/dashboard`.
- [x] 8.4 `openspec validate --all` reports the same pass count as before the change,
      the pre-existing `spec/typed-game-actions` failure aside.
- [x] 8.5 Grep this change directory for the placeholder markers root `AGENTS.md`
      forbids and confirm every artifact is real prose, with no section left empty
      and no heading standing in for content that was never written.
