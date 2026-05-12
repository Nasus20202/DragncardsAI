import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import { PlaySessionList } from "@/features/play/components/play-session-list";
import { SessionSummary } from "@/features/shared/lib/types";

const sessions: SessionSummary[] = [
  {
    id: "session-1",
    name: "session-1234567890123456789012345",
    status: "active",
    context_recent_message_limit: null,
    context_recent_tool_exchange_limit: null,
    metadata: {},
    created_at: "2026-05-11T00:00:00Z",
    updated_at: "2026-05-11T00:00:00Z",
    terminated_at: null,
    model_config: {
      provider_id: "openai",
      model_name: "openrouter/openrouter/free",
      gateway_options: {},
      provider_options: {},
      updated_at: "2026-05-11T00:00:00Z",
    },
    skills: [],
    mcps: [],
    recent_job: {
      id: "job-1",
      prompt: "Hello",
      metadata: {},
      status: "running",
      attempts: 1,
      max_attempts: 1,
      error_code: null,
      error_message: null,
      result_text: null,
      cancellation_requested_at: null,
      created_at: "2026-05-11T00:00:00Z",
      started_at: null,
      completed_at: null,
      latest_event_id: null,
      latest_event_type: null,
    },
  },
  {
    id: "session-2",
    name: null,
    status: "terminated",
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
  },
];

describe("PlaySessionList", () => {
  it("renders expanded list details and selection state", () => {
    render(
      <PlaySessionList
        sessions={sessions}
        selectedSessionId="session-1"
        streamingSessionId={null}
        isBusy={false}
        canCreate={true}
        isCollapsed={false}
        onCreate={vi.fn()}
        onToggleCollapsed={vi.fn()}
        onSelect={vi.fn()}
      />
    );

    expect(screen.getByText("Sessions")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /session-1234567890123456789012345/i })
    ).toHaveAttribute("aria-current", "true");
    expect(screen.getByText(/free · active/i)).toBeInTheDocument();
    expect(screen.getByText("Untitled")).toBeInTheDocument();
    expect(screen.getByText(/No model · terminated/i)).toBeInTheDocument();
  });

  it("uses collapsed controls and invokes callbacks", () => {
    const onCreate = vi.fn();
    const onToggleCollapsed = vi.fn();
    const onSelect = vi.fn();

    render(
      <PlaySessionList
        sessions={sessions}
        selectedSessionId={null}
        streamingSessionId={null}
        isBusy={false}
        canCreate={true}
        isCollapsed={true}
        onCreate={onCreate}
        onToggleCollapsed={onToggleCollapsed}
        onSelect={onSelect}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /new session/i }));
    fireEvent.click(screen.getByRole("button", { name: /expand sidebar/i }));
    fireEvent.click(screen.getByRole("button", { name: /untitled session/i }));

    expect(onCreate).toHaveBeenCalledOnce();
    expect(onToggleCollapsed).toHaveBeenCalledOnce();
    expect(onSelect).toHaveBeenCalledWith("session-2");
  });

  it("disables creation while busy", () => {
    render(
      <PlaySessionList
        sessions={[]}
        selectedSessionId={null}
        streamingSessionId={null}
        isBusy={true}
        canCreate={true}
        isCollapsed={false}
        onCreate={vi.fn()}
        onToggleCollapsed={vi.fn()}
        onSelect={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: /new session/i })).toBeDisabled();
    expect(screen.getByText("No sessions yet.")).toBeInTheDocument();
  });
});
