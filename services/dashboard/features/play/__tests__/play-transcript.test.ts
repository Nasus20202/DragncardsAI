import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { createElement } from "react";

import { PlayTranscript } from "@/features/play/components/play-transcript";
import {
  aggregateEvents,
  STREAM_EVENT_TYPES,
  TERMINAL_EVENT_TYPES,
} from "@/features/play/lib/play-session-events";
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

  it("subscribes to turn_continued on the SSE stream", () => {
    // Without this the marker only ever appears after a reconnect replays it.
    expect(STREAM_EVENT_TYPES).toContain("turn_continued");
  });

  it("does not treat a continued turn as a terminal event", () => {
    // The turn is still running: closing the stream on it would strand every
    // client watching the rest of the answer.
    expect(TERMINAL_EVENT_TYPES.has("turn_continued")).toBe(false);
  });

  it("passes turn_continued through aggregation rather than as a tool call", () => {
    // The aggregator's fallback branch renders an unknown type as a pending
    // tool card that never completes, which is wrong rather than merely blank.
    const aggregated = aggregateEvents(
      [
        {
          id: "1",
          event_type: "turn_continued",
          payload: { reason: "output_token_limit", finish_reason: "length" },
          created_at: "2026-05-11T00:00:01Z",
        },
      ],
      false
    );

    expect(aggregated).toHaveLength(1);
    expect(aggregated[0].kind).toBe("turn_continued");
  });

  it("renders a seam between the partial output and the output that continued it", () => {
    HTMLElement.prototype.scrollIntoView = () => {};

    const job = makeJob([
      {
        id: "1",
        event_type: "model_output",
        payload: { text: "First I will check the" },
        created_at: "2026-05-11T00:00:01Z",
      },
      {
        id: "2",
        event_type: "turn_continued",
        payload: {
          reason: "output_token_limit",
          finish_reason: "length",
          continuation: 1,
          max_continuations: 3,
        },
        created_at: "2026-05-11T00:00:02Z",
      },
      {
        id: "3",
        event_type: "model_output",
        payload: { text: " board state." },
        created_at: "2026-05-11T00:00:03Z",
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

    const seam = screen.getByTestId("play-turn-continued");
    expect(seam.textContent).toContain("turn continued automatically");
    expect(seam.textContent).toContain("length");
    expect(seam.textContent).toContain("continuation 1 of 3");
    // Both halves of the answer survive around it.
    expect(screen.getByText(/First I will check the/)).toBeDefined();
    expect(screen.getByText(/board state\./)).toBeDefined();
  });
});
