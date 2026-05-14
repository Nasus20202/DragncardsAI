import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import {
  getApi,
  installMatchMedia,
  renderPlayWorkspace,
  resetPlayWorkspaceEnvironment,
  sessionSummary,
} from "@/features/play/__tests__/play-workspace-test-support";

const api = getApi();

describe("PlayWorkspace session selection", () => {
  beforeEach(() => {
    resetPlayWorkspaceEnvironment();
  });

  it("loads config, restores the session from the url, and avoids syncing unchanged model config", async () => {
    window.history.replaceState({}, "", "/play?session=session-1");
    globalThis.localStorage.setItem(
      "play:selectedSessionId",
      "different-session"
    );

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("selected-session-id")).toHaveTextContent(
        "session-1"
      )
    );
    await waitFor(() =>
      expect(screen.getByTestId("selected-session-name")).toHaveTextContent(
        "Existing session"
      )
    );
    expect(api.setModelConfig).not.toHaveBeenCalled();
  });

  it("falls back to saved session when the url has no session id", async () => {
    globalThis.localStorage.setItem("play:selectedSessionId", "session-1");

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("selected-session-id")).toHaveTextContent(
        "session-1"
      )
    );
    await waitFor(() =>
      expect(screen.getByTestId("selected-session-name")).toHaveTextContent(
        "Existing session"
      )
    );
    expect(screen.getByTestId("job-count")).toHaveTextContent("1");
    expect(screen.getByTestId("provider-count")).toHaveTextContent("2");
    expect(screen.getByTestId("model-options")).toHaveTextContent(
      "gpt-4o-mini"
    );
    expect(api.setModelConfig).not.toHaveBeenCalled();
  });

  it("switches to mobile defaults on first render", async () => {
    installMatchMedia(true);

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("config-open")).toHaveTextContent("false")
    );
    expect(screen.getByTestId("session-sidebar").className).toContain("w-11");
  });

  it("updates the url when selecting a session", async () => {
    api.listSessions.mockResolvedValue([
      sessionSummary,
      { ...sessionSummary, id: "session-2", name: "Second session" },
    ]);

    renderPlayWorkspace();

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /second session/i })
      ).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole("button", { name: /second session/i }));

    await waitFor(() =>
      expect(screen.getByTestId("selected-session-id")).toHaveTextContent(
        "session-2"
      )
    );
    expect(window.location.search).toBe("?session=session-2");
  });
});
