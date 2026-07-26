import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import {
  getApi,
  renderPlayWorkspace,
  resetPlayWorkspaceEnvironment,
} from "@/features/play/__tests__/play-workspace-test-support";

const api = getApi();

describe("PlayWorkspace initial loading", () => {
  beforeEach(() => {
    resetPlayWorkspaceEnvironment();
  });

  it("surfaces a visible error when the sessions fetch fails", async () => {
    api.listSessions.mockRejectedValue(new Error("sessions down"));

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("error-text")).toHaveTextContent(
        /failed to load sessions/i
      )
    );
  });

  it("surfaces a visible error when the skills fetch fails", async () => {
    api.listAvailableSkills.mockRejectedValue(new Error("skills down"));

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("error-text")).toHaveTextContent(
        /failed to load skills/i
      )
    );
  });

  it("combines the message when both sessions and skills fail", async () => {
    api.listSessions.mockRejectedValue(new Error("sessions down"));
    api.listAvailableSkills.mockRejectedValue(new Error("skills down"));

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("error-text")).toHaveTextContent(
        /failed to load sessions and skills/i
      )
    );
  });

  it("keeps providers degradation graceful without a fatal error", async () => {
    api.listProviders.mockRejectedValue(new Error("providers down"));

    renderPlayWorkspace();

    // Providers failing shows a non-blocking notice, not the fatal error text.
    await waitFor(() =>
      expect(screen.getByTestId("providers-notice")).toBeInTheDocument()
    );
    expect(screen.getByTestId("error-text")).toHaveTextContent("");
  });
});
