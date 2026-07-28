# Tasks

## 1. Session deletion in the orchestrator

- [x] 1.1 Add `Repository.delete_session` deleting the session and every dependent
      row (model config, enabled skills, enabled MCPs, player configs, jobs,
      transcript events, job outputs, compaction records) in one transaction, and
      returning `False` for an unknown session.
- [x] 1.2 Delete each dependent table explicitly instead of relying on the
      declared `ON DELETE CASCADE`, since SQLite does not enforce foreign keys
      without a pragma and `compaction_records` has no ORM cascade from
      `AgentSession`; clear `parent_job_id` on jobs in other sessions that point at
      a deleted job.
- [x] 1.3 Add `DELETE /sessions/{session_id}` returning 204, or 404 when the
      session does not exist, requesting cancellation for queued and running jobs
      before deleting.
- [x] 1.4 Cover it with a repository test asserting no rows survive in any
      session-scoped table (and that global registries and unrelated sessions do),
      a 404 test, a detached-subagent-child test, an API test that deletes a
      session with a queued job, and a Postgres-backed test that proves the delete
      order satisfies enforced foreign keys.

## 2. Deletion in the dashboard

- [x] 2.1 Add `deleteSession` to the Play client API, calling
      `DELETE /sessions/{id}` through the dashboard proxy.
- [x] 2.2 Point `removeSession` at it instead of `terminateSession`, keeping the
      existing post-removal reselection, and report deletion in the status text.
- [x] 2.3 Reword the confirmation dialog and its action to describe a permanent
      deletion with running work cancelled first, and relabel the session list's
      per-session control accordingly.
- [x] 2.4 Update the workspace removal tests to expect a delete, with the session
      absent from the refreshed listing rather than returned as terminated.

## 3. Settings that survive a reload

- [x] 3.1 Add `features/play/lib/last-used-draft.ts` storing the last committed
      configuration in `localStorage` under `play:lastUsedDraft`, validating the
      stored shape on read, dropping the session name, and treating unavailable or
      full storage as "no preference".
- [x] 3.2 Write it from the commit paths only — session creation, an explicit
      configuration save, and the provider/model change that is committed
      immediately — so a half-typed advanced-JSON field is never persisted.
- [x] 3.3 Seed the initial draft from it when present, still letting a session the
      user opens replace the draft with its own settings.
- [x] 3.4 Cover the storage round-trip, its rejection of malformed payloads,
      seeding on a fresh visit, the fallback to configuration defaults, and that an
      opened session's settings win.

## 4. Transcript follow lock

- [x] 4.1 Release the lock on a user gesture — upward wheel, `ArrowUp`/`PageUp`/
      `Home`, or a touch drag downwards — bypassing the programmatic-scroll guard
      that streaming keeps re-arming, and pin the container at its current offset so
      the in-flight smooth scroll cannot continue.
- [x] 4.2 Scroll the container itself rather than the bottom sentinel, so following
      lands at the true bottom instead of leaving the container's padding below the
      fold, and tighten the at-bottom tolerance to sub-pixel rounding.
- [x] 4.3 Re-engage on scrolling back to the bottom and on the existing
      jump-to-latest control, relabelled to describe resuming the follow.
- [x] 4.4 Observe the content box: while locked, follow late growth the job list
      does not report; while released, re-engage once the content fits one viewport
      so the control is never stranded with nowhere to scroll.
- [x] 4.5 Cover engage/disengage/re-engage for wheel, keyboard, touch, the control,
      manual return to the bottom, and both resize directions.

## 5. Model selection with a degraded catalogue

- [x] 5.1 Judge provider usability with `isWorking` (available and offering at
      least one model) when building the notice, so a provider whose key is missing
      is named instead of silently passing as available.
- [x] 5.2 Label providers that offer no models in the provider picker and make them
      non-selectable, leaving a session already pinned to one able to move to a
      working provider.
- [x] 5.3 Extract `withUsableProviderModel` and treat an empty catalogue as "no
      information" rather than a reason to reset the carried provider and model.
- [x] 5.4 Cover the degraded catalogue against the real settings panel — labelled
      and disabled providers, moving to a working provider, a still-usable model
      picker — plus the notice wording and the empty-catalogue carry-forward.
