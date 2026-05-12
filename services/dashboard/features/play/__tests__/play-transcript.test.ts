import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { createElement } from "react";

import { PlayTranscript } from "@/features/play/components/play-transcript";
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
});
