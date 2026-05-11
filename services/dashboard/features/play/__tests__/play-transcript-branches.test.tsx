import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import { PlayTranscript } from "@/features/play/components/play-transcript";
import {
  JobDetail,
  JobEventResponse,
  SessionDetail,
} from "@/features/shared/lib/types";

HTMLElement.prototype.scrollIntoView = vi.fn();

const selectedSession: SessionDetail = {
  id: "session-1",
  name: "Session",
  status: "active",
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

function makeJob(events: JobEventResponse[], prompt = "Prompt"): JobDetail {
  return {
    id: "job-1",
    prompt_run_id: "prompt-run-1",
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
    latest_event_id: events.at(-1)?.id ?? null,
    latest_event_type: events.at(-1)?.event_type ?? null,
    prompt_run: {
      id: "prompt-run-1",
      prompt,
      status: "completed",
      metadata: {},
      created_at: "2026-05-11T00:00:00Z",
      updated_at: "2026-05-11T00:00:02Z",
    },
    outputs: [],
    events,
    available_tools: [],
  };
}

describe("PlayTranscript branches", () => {
  it("renders empty states and status banner", () => {
    const { rerender } = render(
      <PlayTranscript
        jobs={[]}
        streamingJobId={null}
        selectedSession={null}
        streamState="idle"
        statusText="Ready"
        isBusy={false}
        errorText={null}
        onOpenSettings={vi.fn()}
        settingsOpen={false}
      />
    );

    expect(
      screen.getByText("Select or create a session to start.")
    ).toBeInTheDocument();

    rerender(
      <PlayTranscript
        jobs={[]}
        streamingJobId={null}
        selectedSession={selectedSession}
        streamState="streaming"
        statusText="Ready"
        isBusy={false}
        errorText="Boom"
        onOpenSettings={vi.fn()}
        settingsOpen={true}
      />
    );

    expect(screen.getByText("Streaming…")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Boom");
    expect(
      screen.getByText("No messages yet. Type a prompt below.")
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /close session settings/i })
    ).toBeInTheDocument();
  });

  it("aggregates reasoning, tool events, compaction, failure, and cancellation", () => {
    const job = makeJob([
      {
        id: "1",
        event_type: "reasoning",
        payload: { text: "Think 1. " },
        created_at: "2026-05-11T00:00:01Z",
      },
      {
        id: "2",
        event_type: "reasoning",
        payload: { text: "Think 2." },
        created_at: "2026-05-11T00:00:02Z",
      },
      {
        id: "3",
        event_type: "tool_call",
        payload: { exposed_tool_name: "search", text: "call" },
        created_at: "2026-05-11T00:00:03Z",
      },
      {
        id: "4",
        event_type: "tool_result",
        payload: { exposed_tool_name: "search", summary_text: "result" },
        created_at: "2026-05-11T00:00:04Z",
      },
      {
        id: "5",
        event_type: "compaction",
        payload: { summary_text: "compacted" },
        created_at: "2026-05-11T00:00:05Z",
      },
      {
        id: "6",
        event_type: "failure",
        payload: { message: "failed badly" },
        created_at: "2026-05-11T00:00:06Z",
      },
      {
        id: "7",
        event_type: "cancellation",
        payload: {},
        created_at: "2026-05-11T00:00:07Z",
      },
    ]);

    render(
      <PlayTranscript
        jobs={[job]}
        streamingJobId={"job-1"}
        selectedSession={selectedSession}
        streamState="idle"
        statusText="Ready"
        isBusy={false}
        errorText={null}
        onOpenSettings={vi.fn()}
        settingsOpen={false}
      />
    );

    expect(screen.getByText("Prompt")).toBeInTheDocument();
    expect(screen.getByText("Reasoning")).toBeInTheDocument();
    expect(screen.getByText("Think 1. Think 2.")).toBeInTheDocument();
    expect(screen.getByText("Context compaction")).toBeInTheDocument();
    expect(screen.getByText("Error")).toBeInTheDocument();
    expect(screen.getByText("failed badly")).toBeInTheDocument();
    expect(screen.getByText("Cancelled")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /expand tool call: search/i })
    );
    fireEvent.click(
      screen.getByRole("button", { name: /expand tool result: search/i })
    );

    expect(screen.getByText("call")).toBeInTheDocument();
    expect(screen.getByText("result")).toBeInTheDocument();
  });

  it("treats compaction payload on model output as a compaction block", () => {
    const job = makeJob(
      [
        {
          id: "1",
          event_type: "model_output",
          payload: { text: "summary", compaction: true },
          created_at: "2026-05-11T00:00:01Z",
        },
      ],
      "[COMPACTION]"
    );

    render(
      <PlayTranscript
        jobs={[job]}
        streamingJobId={null}
        selectedSession={selectedSession}
        streamState="idle"
        statusText="Ready"
        isBusy={false}
        errorText={null}
        onOpenSettings={vi.fn()}
        settingsOpen={false}
      />
    );

    expect(screen.getByText("Context compaction")).toBeInTheDocument();
    expect(screen.queryByText("[COMPACTION]")).toBeNull();
  });

  it("auto-collapses reasoning once output arrives", () => {
    const { rerender } = render(
      <PlayTranscript
        jobs={[
          makeJob([
            {
              id: "1",
              event_type: "reasoning",
              payload: { text: "hidden later" },
              created_at: "2026-05-11T00:00:01Z",
            },
          ]),
        ]}
        streamingJobId={"job-1"}
        selectedSession={selectedSession}
        streamState="idle"
        statusText="Ready"
        isBusy={false}
        errorText={null}
        onOpenSettings={vi.fn()}
        settingsOpen={false}
      />
    );

    expect(
      screen.getByRole("button", { name: /collapse reasoning/i })
    ).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("hidden later")).toBeInTheDocument();

    rerender(
      <PlayTranscript
        jobs={[
          makeJob([
            {
              id: "1",
              event_type: "reasoning",
              payload: { text: "hidden later" },
              created_at: "2026-05-11T00:00:01Z",
            },
            {
              id: "2",
              event_type: "model_output",
              payload: { text: "final text" },
              created_at: "2026-05-11T00:00:02Z",
            },
          ]),
        ]}
        streamingJobId={"job-1"}
        selectedSession={selectedSession}
        streamState="idle"
        statusText="Ready"
        isBusy={false}
        errorText={null}
        onOpenSettings={vi.fn()}
        settingsOpen={false}
      />
    );

    const toggle = screen.getByRole("button", { name: /expand reasoning/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("hidden later")).toBeNull();
    expect(screen.getByText("final text")).toBeInTheDocument();
  });
});
