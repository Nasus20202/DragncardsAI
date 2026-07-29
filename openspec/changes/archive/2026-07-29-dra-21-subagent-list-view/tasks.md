# Tasks

## 1. Establish where the names and the list actually come from

- [x] 1.1 Confirm the subagent name is `prompt[:50]`, set in
      `make_spawn_subagent_handler` and passed through `_launch_child_agent` into
      the child session row, the `subagent_started` payload, the monitor's outcome
      events and the tool result.
- [x] 1.2 Confirm the session name is `buildDefaultSessionName()` (a timestamp) at
      creation and `prompt.slice(0, 60)` via `updateSession` on the first prompt,
      both in the dashboard.
- [x] 1.3 Confirm which of the two `SubagentList` components the Play workspace
      renders: the one in `features/play/components/subagent-list.tsx`. The one in
      `subagent-card.tsx` is unreferenced.
- [x] 1.4 Confirm no migration is needed: `agent_sessions.name` already exists and
      `job_events.payload` is free-form JSON. The highest existing migration is
      `0010_job_questions` and stays that way.
- [x] 1.5 Confirm DRA-22's **View subagent** button reads the child's name out of
      the tool result, so it inherits generated names with no change.

## 2. Generate the names (agent-orchestrator)

- [x] 2.1 Add `runtime/display_names.py` with `generate_agent_name(seed, text)`,
      a `blake2b`-seeded codename over 32 adjectives and 32 animals, and a topic
      mined from the prompt's content words.
- [x] 2.2 Reject an atom whole unless every underscore-separated part of it is
      alphabetic and all-lower, all-upper or capitalised, so identifiers and
      credential-shaped strings contribute nothing.
- [x] 2.3 Exclude function words and the orchestrator's instruction boilerplate,
      deduplicate words, and build the topic under a character budget so it never
      ends part-way through a word.
- [x] 2.4 Bound the whole name so it fits the `String(255)` column and the
      controls that display it.

## 3. Name the subagents (agent-orchestrator)

- [x] 3.1 Make `_launch_child_agent` take `name: str | None`, create the child
      session unnamed when it is `None`, generate the name from the child session's
      own id and the prompt, and store it with one `update_session`.
- [x] 3.2 Have `spawn_subagent` pass `name=None`, so its child is named rather
      than labelled with a slice of its prompt.
- [x] 3.3 Leave `prompt_player_agent` passing its seat's display name, which is
      already meaningful, and confirm the supplied name wins.
- [x] 3.4 Confirm the generated name reaches the `subagent_started` payload, the
      monitor's outcome events and the tool result from that one generation.

## 4. Name the sessions (agent-orchestrator)

- [x] 4.1 In `POST /sessions/{id}/prompts`, read the session and its job count
      before enqueuing so "first prompt" is decided without counting the new job.
- [x] 4.2 Generate and store a name when the session has no name and no prior job;
      leave a named session and a session that has already run untouched.

## 5. Stop the dashboard deriving names

- [x] 5.1 Replace `buildDefaultSessionName()` with an unnamed draft in
      `createDefaultDraft` and `createNewSessionDraft`, and delete the function.
- [x] 5.2 Remove the first-prompt `updateSession({ name: prompt.slice(0, 60) })`
      from `submitSessionPrompt`, keeping the session-list refresh that now shows
      the generated name.
- [x] 5.3 Make `saveConfiguration` send `null` rather than inventing a name, so
      saving settings on a fresh session does not consume its chance to be named.
- [x] 5.4 Confirm the sidebar already renders a placeholder for a session with no
      name, so an unprompted session stays selectable.

## 6. Bound and scroll the list (dashboard)

- [x] 6.1 Put the entries in a container with `max-h-[min(45vh,16rem)]`,
      `overflow-y-auto` and `overscroll-contain`, inside the component rather than
      on the workspace's absolutely positioned wrapper.
- [x] 6.2 Keep the header and the filter outside the scroll area so they do not
      scroll away from the list they control.
- [x] 6.3 Widen the entry's name truncation and add the full name as a `title`,
      since a generated name is longer than the row.

## 7. Filter the list by status (dashboard)

- [x] 7.1 Add `features/play/lib/subagent-filter.ts` with the filter options, the
      type guard, `filterSubagentsByStatus`, `countSubagentsByStatus` and
      `attentionSubagents` (the collapsed view's running-and-failed selection).
- [x] 7.2 Build the control from Hero UI's `ToggleButtonGroup` in single-selection
      mode with `disallowEmptySelection`, sized to the list's 10px chrome, each
      button labelled with its count.
- [x] 7.3 Show the filter only when the list is expanded; keep the collapsed list
      showing exactly what it showed before.
- [x] 7.4 State that nothing holds the chosen status instead of showing an empty
      box.

## 8. Redaction and dead code (dashboard)

- [x] 8.1 Redact the displayed entry name and failure reason with the same
      `redactSecrets` the tool cards use, because names stored before this change
      are raw slices of model-written prompts.
- [x] 8.2 Redact the name in the subagent output view's header for the same
      reason.
- [x] 8.3 Delete the unreferenced `subagent-card.tsx`, which held a second,
      unbounded subagent list that nothing rendered.

## 9. Tests

- [x] 9.1 `tests/unit/test_display_names.py`: determinism, distinguishability
      across seeds, two identical prompts differing, topic taken from the task not
      the boilerplate, tool names contributing their words, identifiers and
      numbers excluded, credential-shaped runs not mined, codename-only fallback,
      deduplication, and bounded output for a 4000-word prompt.
- [x] 9.2 `tests/unit/test_builtin_tools_subagents.py`: the child session's stored
      name, the `subagent_started` payload and the tool result all carry the one
      generated name, and its topic comes from the prompt.
- [x] 9.3 `tests/unit/test_app_jobs.py`: an unnamed session is named by its first
      prompt, a second prompt does not rename it, a named session keeps its name,
      and a session created with no name at all is named.
- [x] 9.4 `features/play/__tests__/subagent-filter.test.ts`: the option list, the
      type guard, filtering per status, the counts agreeing with the filter they
      label, and the collapsed view's selection.
- [x] 9.5 `features/play/__tests__/subagent-list.test.tsx`: the bounded scrolling
      container and its classes, all thirty entries present inside it, the
      collapsed running-and-failed view, the filter appearing only when expanded,
      its counts, narrowing per status, returning to All, the empty-status note,
      the job-id fallback, redaction of a legacy name, and selection.
- [x] 9.6 `features/play/__tests__/play-workspace-execution.test.tsx`: submitting a
      prompt does not patch the session name and does refresh the session list.
- [x] 9.7 `features/play/__tests__/session-draft.test.ts`: a new session draft is
      unnamed, from defaults and from a carried last-used draft.

## 10. Surrounding files

- [x] 10.1 Confirm no README, environment variable, port, container, script, make
      target or API shape is made stale: the endpoints, payload keys and tool
      results keep their shapes, and no README documents how a name is derived.
- [x] 10.2 Correct the `llm-capabilities` requirement that pointed at the "inline
      subagent card" for a child's transcript, which the deleted component was.

## 11. Verification

- [x] 11.1 `./scripts/lint.sh --fix` clean.
- [x] 11.2 `pnpm typecheck` clean in `services/dashboard`.
- [x] 11.3 `./scripts/test.sh unit` passes; agent-orchestrator 431 → 437 and
      dashboard 516 → 544, other services unchanged.
- [x] 11.4 `./scripts/test.sh integration agent-orchestrator` passes.
- [x] 11.5 `openspec validate --all` reports the same failures as before the
      change — the pre-existing `spec/typed-game-actions` one only.
