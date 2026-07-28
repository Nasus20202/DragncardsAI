import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render } from "@testing-library/react";

import { JobDetail, SessionDetail } from "@/features/shared/lib/types";

/**
 * Counts how often the markdown renderer runs. Rendering model output is the most
 * expensive thing the transcript does, and before the blocks were memoised every
 * settled response in the session re-rendered — and re-parsed its markdown — on
 * every streamed token, so the cost of one token grew with the length of the
 * history. This counter is the regression guard for that.
 */
const markdownRenders = vi.fn();
vi.mock("react-markdown", () => ({
  default: ({ children }: { children?: string }) => {
    markdownRenders();
    return <div>{children}</div>;
  },
}));

const { PlayTranscript } =
  await import("@/features/play/components/play-transcript");

const selectedSession: SessionDetail = {
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
};

function makeJob(id: string, text: string, status: string): JobDetail {
  return {
    id,
    prompt: `Prompt ${id}`,
    metadata: {},
    status,
    attempts: 1,
    max_attempts: 1,
    error_code: null,
    error_message: null,
    result_text: null,
    cancellation_requested_at: null,
    created_at: "2026-05-11T00:00:00Z",
    started_at: null,
    completed_at: null,
    latest_event_id: "1",
    latest_event_type: "model_output",
    outputs: [],
    events: [
      {
        id: `${id}-1`,
        event_type: "model_output",
        payload: { text },
        created_at: "2026-05-11T00:00:01Z",
      },
    ],
    available_tools: [],
  };
}

function transcript(jobs: JobDetail[]) {
  return (
    <PlayTranscript
      jobs={jobs}
      streamingJobId="job-3"
      selectedSession={selectedSession}
      streamState="streaming"
      statusText="Ready"
      isBusy={false}
      errorText={null}
      onOpenSettings={vi.fn()}
      settingsOpen={false}
    />
  );
}

describe("PlayTranscript re-render cost", () => {
  beforeEach(() => {
    markdownRenders.mockClear();
    Object.defineProperty(globalThis, "ResizeObserver", {
      configurable: true,
      writable: true,
      value: class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    });
    HTMLElement.prototype.scrollTo = vi.fn();
    HTMLElement.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("re-renders only the streaming response when a token arrives", () => {
    const settled = [
      makeJob("job-1", "first answer", "completed"),
      makeJob("job-2", "second answer", "completed"),
    ];
    const jobs = [...settled, makeJob("job-3", "third", "running")];

    let rerender: (ui: React.ReactElement) => void = () => {};
    act(() => {
      rerender = render(transcript(jobs)).rerender;
    });
    expect(markdownRenders).toHaveBeenCalledTimes(3);

    // Exactly what `applyStreamEventToJob` produces for one token: a new events
    // array and a new jobs array, with every settled job kept by identity.
    markdownRenders.mockClear();
    act(() => {
      rerender(
        transcript([...settled, makeJob("job-3", "third and more", "running")])
      );
    });

    expect(markdownRenders).toHaveBeenCalledTimes(1);
  });

  it("keeps the whole transcript out of the render when nothing changed", () => {
    const jobs = [
      makeJob("job-1", "first answer", "completed"),
      makeJob("job-2", "second answer", "completed"),
      makeJob("job-3", "third", "running"),
    ];

    let rerender: (ui: React.ReactElement) => void = () => {};
    act(() => {
      rerender = render(transcript(jobs)).rerender;
    });

    markdownRenders.mockClear();
    act(() => {
      rerender(transcript([...jobs]));
    });

    expect(markdownRenders).not.toHaveBeenCalled();
  });
});
