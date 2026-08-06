import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import {
  createQueuedJob,
  getApi,
  job,
  renderPlayWorkspace,
  resetPlayWorkspaceEnvironment,
} from "@/features/play/__tests__/play-workspace-test-support";

const api = getApi();

describe("PlayWorkspace execution", () => {
  beforeEach(() => {
    resetPlayWorkspaceEnvironment();
  });

  it("submits a prompt and refreshes the job list", async () => {
    api.submitPrompt.mockResolvedValueOnce(createQueuedJob());
    api.getJob
      .mockResolvedValueOnce(job)
      .mockResolvedValueOnce(createQueuedJob());

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("prompt-session")).toHaveTextContent(
        "session-1"
      )
    );
    fireEvent.change(screen.getByLabelText("Prompt input"), {
      target: { value: "Hello world" },
    });
    fireEvent.click(screen.getByRole("button", { name: /submit prompt/i }));

    await waitFor(() =>
      expect(api.submitPrompt).toHaveBeenCalledWith(
        "session-1",
        "Hello world",
        []
      )
    );
    // Awaited, not queried synchronously: `submitPrompt` having been *called* is
    // the first step of the handler, and the banner only renders once the
    // follow-up `getJob` has resolved and streaming has started two awaits
    // later. A synchronous query here races that render and loses whenever the
    // machine is busy enough to push the chain past the one `setTimeout(0)` of
    // grace Testing Library allows it.
    expect(
      await screen.findByRole("status", { name: /streaming response/i })
    ).toBeInTheDocument();
    // Committed in the same render as the banner, so these cannot be early.
    expect(screen.getByText("Streaming response...")).toBeInTheDocument();
    expect(screen.getByTestId("active-job-id")).toHaveTextContent("job-2");
  });

  it("requests cancellation for the active execution", async () => {
    api.submitPrompt.mockResolvedValueOnce(createQueuedJob());
    api.getJob
      .mockResolvedValueOnce(job)
      .mockResolvedValueOnce(createQueuedJob());

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("prompt-session")).toHaveTextContent(
        "session-1"
      )
    );
    fireEvent.change(screen.getByLabelText("Prompt input"), {
      target: { value: "Hello world" },
    });
    fireEvent.click(screen.getByRole("button", { name: /submit prompt/i }));

    await waitFor(() =>
      expect(screen.getByTestId("active-job-id")).toHaveTextContent("job-2")
    );

    fireEvent.click(screen.getByRole("button", { name: /cancel execution/i }));

    await waitFor(() => expect(api.cancelJob).toHaveBeenCalledWith("job-2"));
    await waitFor(() =>
      expect(screen.getByTestId("cancel-pending")).toHaveTextContent("true")
    );
  });

  it("compacts context and reloads jobs", async () => {
    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("prompt-session")).toHaveTextContent(
        "session-1"
      )
    );
    fireEvent.click(screen.getByRole("button", { name: /compact context/i }));

    await waitFor(() =>
      expect(api.compactSession).toHaveBeenCalledWith("session-1")
    );
    expect(api.listSessionJobs).toHaveBeenCalledWith("session-1");
  });

  it("does not name the session from the prompt it submits", async () => {
    // Naming an unnamed session from its first prompt belongs to the
    // orchestrator, which does it inside the same request. The dashboard used to
    // derive `prompt.slice(0, 60)` here; deriving it per client is exactly what
    // stops two browsers agreeing on a session's name.
    api.submitPrompt.mockResolvedValueOnce(createQueuedJob());
    api.getJob
      .mockResolvedValueOnce(job)
      .mockResolvedValueOnce(createQueuedJob());
    api.listSessionJobs.mockResolvedValueOnce({ jobs: [], total: 0 });

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("prompt-session")).toHaveTextContent(
        "session-1"
      )
    );
    fireEvent.change(screen.getByLabelText("Prompt input"), {
      target: { value: "Deal the encounter card to Rhino" },
    });
    fireEvent.click(screen.getByRole("button", { name: /submit prompt/i }));

    await waitFor(() => expect(api.submitPrompt).toHaveBeenCalled());
    // The list is refreshed so the name the orchestrator generated shows up.
    await waitFor(() => expect(api.listSessions).toHaveBeenCalled());
    expect(api.updateSession).not.toHaveBeenCalled();
  });
});
