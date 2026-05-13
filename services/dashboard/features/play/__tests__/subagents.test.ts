import { describe, expect, it } from "vitest";
import { deriveSubagentEntries } from "@/features/play/lib/play-session-events";
import { JobDetail } from "@/features/shared/lib/types";

function makeJob(
  events: { event_type: string; payload: Record<string, unknown> }[]
): JobDetail {
  return {
    id: "job-1",
    status: "completed",
    prompt: "go",
    metadata: {},
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    started_at: null,
    completed_at: null,
    error_code: null,
    error_message: null,
    parent_job_id: null,
    job_type: "prompt",
    latest_event_id: null,
    latest_event_type: null,
    outputs: [],
    events: events.map((e, i) => ({
      id: String(i),
      event_type: e.event_type,
      payload: e.payload,
      created_at: "2026-01-01T00:00:00Z",
    })),
  } as unknown as JobDetail;
}

describe("deriveSubagentEntries", () => {
  it("returns running when subagent_started has no outcome event", () => {
    const job = makeJob([
      {
        event_type: "subagent_started",
        payload: {
          child_job_id: "child-1",
          child_session_id: "sess-1",
          name: "do thing",
        },
      },
    ]);
    const entries = deriveSubagentEntries([job]);
    expect(entries).toHaveLength(1);
    expect(entries[0].status).toBe("running");
  });

  it("resolves to completed when subagent_completed event present", () => {
    const job = makeJob([
      {
        event_type: "subagent_started",
        payload: {
          child_job_id: "child-1",
          child_session_id: "sess-1",
          name: "do thing",
        },
      },
      {
        event_type: "subagent_completed",
        payload: {
          child_job_id: "child-1",
          child_session_id: "sess-1",
          name: "do thing",
        },
      },
    ]);
    const entries = deriveSubagentEntries([job]);
    expect(entries[0].status).toBe("completed");
  });

  it("reconciles orphaned running entry to completed via childJobStatuses", () => {
    const job = makeJob([
      {
        event_type: "subagent_started",
        payload: {
          child_job_id: "child-1",
          child_session_id: "sess-1",
          name: "do thing",
        },
      },
    ]);
    const statuses = new Map([["child-1", "completed"]]);
    const entries = deriveSubagentEntries([job], statuses);
    expect(entries[0].status).toBe("completed");
  });

  it("reconciles orphaned running entry to failed via childJobStatuses", () => {
    const job = makeJob([
      {
        event_type: "subagent_started",
        payload: {
          child_job_id: "child-1",
          child_session_id: "sess-1",
          name: "do thing",
        },
      },
    ]);
    const statuses = new Map([["child-1", "failed"]]);
    const entries = deriveSubagentEntries([job], statuses);
    expect(entries[0].status).toBe("failed");
  });

  it("does not override already-resolved entries via childJobStatuses", () => {
    const job = makeJob([
      {
        event_type: "subagent_started",
        payload: {
          child_job_id: "child-1",
          child_session_id: "sess-1",
          name: "do thing",
        },
      },
      {
        event_type: "subagent_completed",
        payload: {
          child_job_id: "child-1",
          child_session_id: "sess-1",
          name: "do thing",
        },
      },
    ]);
    // Stale map entry should not override event-derived status
    const statuses = new Map([["child-1", "failed"]]);
    const entries = deriveSubagentEntries([job], statuses);
    expect(entries[0].status).toBe("completed");
  });

  it("leaves entry running when childJobStatuses shows still running", () => {
    const job = makeJob([
      {
        event_type: "subagent_started",
        payload: {
          child_job_id: "child-1",
          child_session_id: "sess-1",
          name: "do thing",
        },
      },
    ]);
    const statuses = new Map([["child-1", "running"]]);
    const entries = deriveSubagentEntries([job], statuses);
    expect(entries[0].status).toBe("running");
  });
});
