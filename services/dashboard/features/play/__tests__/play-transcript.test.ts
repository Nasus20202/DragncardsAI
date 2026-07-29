import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { createElement } from "react";

import { PlayTranscript } from "@/features/play/components/play-transcript";
import { STREAM_EVENT_TYPES } from "@/features/play/lib/play-session-events";
import { JobDetail, SessionDetail } from "@/features/shared/lib/types";

const selectedSession = {
  id: "session-1",
  name: "Session",
  status: "active",
  context_recent_message_limit: null,
  context_recent_tool_exchange_limit: null,
  metadata: {},
  created_at: "2026-05-11T00:00:00Z",
  updated_at: "2026-05-11T00:00:00Z",
  terminated_at: null,
  model_config: null,
  skills: [],
  mcps: [],
  recent_job: null,
  recent_jobs: [],
} satisfies SessionDetail;

function makeJob(events: JobDetail["events"]): JobDetail {
  return {
    id: "job-1",
    prompt: "Who is logenz?",
    metadata: {},
    status: "completed",
    attempts: 1,
    max_attempts: 1,
    error_code: null,
    error_message: null,
    result_text: null,
    cancellation_requested_at: null,
    created_at: "2026-05-11T00:00:00Z",
    started_at: "2026-05-11T00:00:01Z",
    completed_at: "2026-05-11T00:00:02Z",
    latest_event_id: "2",
    latest_event_type: "completion",
    outputs: [],
    events,
    available_tools: [],
  };
}

describe("PlayTranscript", () => {
  it("prefers completion text over partial streamed model output", () => {
    HTMLElement.prototype.scrollIntoView = () => {};

    const job = makeJob([
      {
        id: "1",
        event_type: "model_output",
        payload: { text: 'I do not have any information about "' },
        created_at: "2026-05-11T00:00:01Z",
      },
      {
        id: "2",
        event_type: "completion",
        payload: {
          text: 'I do not have any information about "logenz" in my knowledge base.',
        },
        created_at: "2026-05-11T00:00:02Z",
      },
    ]);

    render(
      createElement(PlayTranscript, {
        jobs: [job],
        streamingJobId: null,
        selectedSession,
        streamState: "idle",
        statusText: "Ready",
        isBusy: false,
        errorText: null,
        onOpenSettings: () => {},
        settingsOpen: false,
      })
    );

    expect(
      screen.getByText(
        'I do not have any information about "logenz" in my knowledge base.'
      )
    ).toBeDefined();
    expect(
      screen.queryByText('I do not have any information about "')
    ).toBeNull();
  });

  it("subscribes to compaction_failed on the SSE stream", () => {
    // Without this the EventSource silently drops it: use-job-streaming
    // registers one named listener per entry and has no onmessage fallback.
    expect(STREAM_EVENT_TYPES).toContain("compaction_failed");
  });

  it("renders a compaction_failed event as a degradation, not as a turn failure", () => {
    HTMLElement.prototype.scrollIntoView = () => {};

    const job = makeJob([
      {
        id: "1",
        event_type: "compaction_failed",
        payload: {
          code: "context_length_exceeded",
          message: "request exceeds the model context window",
          usage_ratio: 0.91,
        },
        created_at: "2026-05-11T00:00:01Z",
      },
      {
        id: "2",
        event_type: "completion",
        payload: { text: "Villain attacks for 3." },
        created_at: "2026-05-11T00:00:02Z",
      },
    ]);

    render(
      createElement(PlayTranscript, {
        jobs: [job],
        streamingJobId: null,
        selectedSession,
        streamState: "idle",
        statusText: "Ready",
        isBusy: false,
        errorText: null,
        onOpenSettings: () => {},
        settingsOpen: false,
      })
    );

    expect(screen.getByText("Context compaction failed")).toBeDefined();
    expect(
      screen.getByText(/request exceeds the model context window/)
    ).toBeDefined();
    expect(
      screen.getByText(/continued on the history it already had/)
    ).toBeDefined();
    // The turn's own answer is still shown: the job completed.
    expect(screen.getByText("Villain attacks for 3.")).toBeDefined();
    expect(screen.queryByText("Error")).toBeNull();
  });
});
