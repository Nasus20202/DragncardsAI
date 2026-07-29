# Tasks

## 1. Confirm the existing paths before changing them

- [x] 1.1 Confirm DRA-11's mention picker removes the `@…` token
      (`removeSkillMention`) and that nothing else uses that helper.
- [x] 1.2 Confirm the worker builds the turn's user message from `full_job.prompt`
      and that history replay reconstructs a prior turn from the stored
      `job.prompt`, so inlining at run time costs context once.
- [x] 1.3 Confirm `load_skill` / `load_skill_reference` reject a skill that is not
      assigned to the session, which is why DRA-11's session attach must stay.

## 2. Orchestrator: carry the loaded skills on the job

- [x] 2.1 Add `JOB_INLINE_SKILLS_KEY`, `MAX_INLINE_SKILLS`, and a renderer that
      turns skill names plus the typed prompt into the turn's user message to
      `runtime/skills.py`.
- [x] 2.2 Add `inline_skills` to `PromptRequest`.
- [x] 2.3 Validate `inline_skills` in `submit_prompt` (resolve each name, bound the
      count, dedupe) and store the validated list in the job metadata, replacing
      any client-supplied value of that key.
- [x] 2.4 Add orchestrator unit tests: renderer output and skipping, endpoint
      acceptance, unknown-name rejection, count bound, dedupe, and the metadata
      forgery case.

## 3. Orchestrator: deliver the content in the turn

- [x] 3.1 In `prompt_run`, build the user message from the recorded skills plus
      `full_job.prompt`, leaving the emitted `user_prompt` event as the typed text.
- [x] 3.2 Record and publish a `skill_loaded` event per skill actually loaded.
- [x] 3.3 Add a worker test asserting the user message the gateway receives carries
      the skill content, the stored prompt does not, and the event is emitted.

## 4. Dashboard: the mention stays in the message

- [x] 4.1 Replace `removeSkillMention` with `completeSkillMention` in
      `features/play/lib/skill-mentions.ts` and add `findMentionedSkillNames`.
- [x] 4.2 Complete the token in `PlayPromptBox` instead of removing it, keeping the
      caret restoration behaviour.
- [x] 4.3 Stop excluding already-attached skills from the picker, so a skill can be
      loaded into a later message as well.
- [x] 4.4 Pass the mentioned skills through `submitPrompt` and
      `submitSessionPrompt`, matched against the session's assigned skills.
- [x] 4.5 Update `skill-mentions.test.ts` and `play-prompt-box-skills.test.tsx`,
      and cover submission naming the mentioned skills.

## 5. Verification

- [x] 5.1 `./scripts/lint.sh --fix` clean.
- [x] 5.2 `./scripts/test.sh unit dashboard agent-orchestrator` passes.
- [x] 5.3 `pnpm typecheck` clean in `services/dashboard`.
- [x] 5.4 `openspec validate --all` reports the same pass count as before the
      change (the pre-existing `spec/typed-game-actions` failure aside).
- [x] 5.5 Sync `openspec/specs/dashboard/spec.md` and
      `openspec/specs/agent-orchestrator/spec.md`.
