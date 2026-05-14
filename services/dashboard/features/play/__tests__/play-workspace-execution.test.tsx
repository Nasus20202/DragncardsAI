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
      expect(api.submitPrompt).toHaveBeenCalledWith("session-1", "Hello world")
    );
    expect(
      screen.getByRole("status", { name: /streaming response/i })
    ).toBeInTheDocument();
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
});
