import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import {
  getApi,
  job,
  renderPlayWorkspace,
  resetPlayWorkspaceEnvironment,
  sessionSummary,
} from "@/features/play/__tests__/play-workspace-test-support";
import type { JobDetail, SessionSummary } from "@/features/shared/lib/types";

const api = getApi();

function summary(overrides: Partial<SessionSummary>): SessionSummary {
  return { ...sessionSummary, ...overrides };
}

describe("PlayWorkspace session removal", () => {
  beforeEach(() => {
    resetPlayWorkspaceEnvironment();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("drops the removed session from the sidebar and reselects the next visible one", async () => {
    const sessionOne = summary({ id: "session-1", name: "First session" });
    const sessionTwo = summary({ id: "session-2", name: "Second session" });
    // Initial load lists both; after removal session-1 comes back terminated.
    api.listSessions
      .mockResolvedValueOnce([sessionOne, sessionTwo])
      .mockResolvedValue([{ ...sessionOne, status: "terminated" }, sessionTwo]);

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("selected-session-id")).toHaveTextContent(
        "session-1"
      )
    );
    expect(screen.getByTestId("visible-session-ids")).toHaveTextContent(
      "session-1,session-2"
    );

    fireEvent.click(screen.getByTestId("remove-session-1"));

    await waitFor(() =>
      expect(api.terminateSession).toHaveBeenCalledWith("session-1")
    );
    // The terminated session disappears from the sidebar state.
    await waitFor(() =>
      expect(screen.getByTestId("visible-session-ids")).toHaveTextContent(
        "session-2"
      )
    );
    expect(screen.getByTestId("visible-session-ids")).not.toHaveTextContent(
      "session-1"
    );
    // Selection moves to the next visible session.
    await waitFor(() =>
      expect(screen.getByTestId("selected-session-id")).toHaveTextContent(
        "session-2"
      )
    );
  });

  it("reselects skipping subagent-child sessions and selects null when none remain", async () => {
    const sessionOne = summary({ id: "session-1", name: "First session" });
    // child-session is a subagent child; the sidebar hides it, so removal must
    // not reselect it.
    const childSession = summary({
      id: "child-session",
      name: "Child session",
    });
    api.listSessions
      .mockResolvedValueOnce([sessionOne, childSession])
      .mockResolvedValue([
        { ...sessionOne, status: "terminated" },
        childSession,
      ]);

    // Give session-1 a job whose event spawns child-session as a subagent.
    const jobWithSubagent: JobDetail = {
      ...job,
      events: [
        {
          id: "event-sub",
          event_type: "subagent_started",
          payload: {
            child_job_id: "child-job",
            child_session_id: "child-session",
            name: "Child",
          },
          created_at: "2026-05-11T00:00:01Z",
        },
      ],
    };
    api.listSessionJobs.mockResolvedValue({
      jobs: [{ ...job, events: undefined }],
      page: { total: 1, limit: 50, offset: 0 },
    });
    api.getJob.mockResolvedValue(jobWithSubagent);

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("selected-session-id")).toHaveTextContent(
        "session-1"
      )
    );
    // The sidebar hides the subagent-child session.
    await waitFor(() =>
      expect(screen.getByTestId("visible-session-ids")).toHaveTextContent(
        "session-1"
      )
    );

    fireEvent.click(screen.getByTestId("remove-session-1"));

    await waitFor(() =>
      expect(api.terminateSession).toHaveBeenCalledWith("session-1")
    );
    // child-session is a subagent child and terminated session-1 is gone, so no
    // selectable session remains and selection clears to null.
    await waitFor(() =>
      expect(screen.getByTestId("selected-session-id")).toHaveTextContent(
        "none"
      )
    );
  });
});
