# Tasks

Ordered so the report is diagnosed before anything is changed, since the change is
only worth making once the diagnosis rules a code defect out.

## 1. Establish what actually happens

- [x] 1.1 Confirm the orchestrator's `PATCH /sessions/{id}` in this tree writes and
      returns `session_persona` and `allowed_subagents` correctly, by calling it
      directly against a current build.
- [x] 1.2 Confirm the deployed orchestrator's `SessionUpdateRequest` carries
      neither field and declares no `additionalProperties`, so both are accepted
      and ignored.
- [x] 1.3 Confirm the deployed orchestrator's database has no
      `session_allowed_subagents` table, so it predates migration `0013`.
- [x] 1.4 Reproduce the report in a browser: current dashboard against a
      pre-DRA-38 orchestrator, allow a persona, save, observe the toggle revert
      and the status line read "Configuration saved".
- [x] 1.5 Confirm the same click against a current orchestrator persists, so the
      difference is the server and not the client.

## 2. Compare what was asked for against what the server has

- [x] 2.1 Add `unappliedSessionSettings(requested, saved)` to
      `features/play/lib/session-draft.ts`, returning the human-readable names of
      the settings the server does not report as asked.
- [x] 2.2 Treat a field missing from the response as unapplied, not as cleared,
      since that is precisely the case the comparison exists for.
- [x] 2.3 Compare the allowlist as a set, so ordering differences between client
      and server are not reported as a failure.

## 3. Report it when saving

- [x] 3.1 In `saveConfiguration`, run the comparison against the session it
      already re-reads, and on a mismatch set the status to "Save incomplete" and
      an error naming the settings and the likely cause.
- [x] 3.2 Leave the draft seeded from what the server reports, so the panel keeps
      showing the truth.
- [x] 3.3 Establish that `createPlaySession` cannot carry the same message: the
      session loader started by selecting the new session reports "Ready" and
      clears the error area before a user could read it. Record that as a
      deliberate exclusion rather than leaving it to look like an omission.

## 4. Cover it

- [x] 4.1 Test that a save whose response omits both fields reports an incomplete
      save naming both settings.
- [x] 4.2 Test that a save whose response echoes both fields reports success.
- [x] 4.3 Test that an allowlist returned in a different order reports success.
- [x] 4.4 Test that the panel still shows the stored settings after an incomplete
      save.

## 5. Verify

- [x] 5.1 Re-run the browser reproduction against the pre-DRA-38 orchestrator and
      confirm the save now reports the failure instead of "Configuration saved".
- [x] 5.2 Re-run it against a current orchestrator and confirm the save still
      reports success.
- [x] 5.3 `./scripts/lint.sh --fix`, `pnpm typecheck`, `./scripts/test.sh unit`,
      `./scripts/test.sh integration`, `openspec validate --all`.
