import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import {
  getApi,
  installMatchMedia,
  renderPlayWorkspace,
  resetPlayWorkspaceEnvironment,
  sessionSummary,
} from "@/features/play/__tests__/play-workspace-test-support";
import type { ContextMetadata } from "@/features/shared/lib/types";

const api = getApi();

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

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

  it("clears context metadata on session change and ignores stale responses", async () => {
    const { promise: session1ContextPromise, resolve: resolveSession1Context } =
      createDeferred<ContextMetadata>();

    api.listSessions.mockResolvedValue([
      sessionSummary,
      { ...sessionSummary, id: "session-2", name: "Second session" },
    ]);
    api.getSession.mockImplementation((id: string) =>
      Promise.resolve({
        ...sessionSummary,
        id,
        name: id === "session-2" ? "Second session" : "Existing session",
        model_config: {
          provider_id: "openai",
          model_name: "gpt-4o-mini",
          gateway_options: {},
          provider_options: {},
          updated_at: "2026-05-11T00:00:00Z",
        },
        recent_jobs: [],
        skills: [],
        mcps: [],
      })
    );
    api.listSessionMcps.mockResolvedValue([]);
    api.listSessionJobs.mockResolvedValue({
      jobs: [],
      page: { total: 0, limit: 50, offset: 0 },
    });
    api.getContextMetadata.mockImplementation((id: string) => {
      if (id === "session-1") {
        return session1ContextPromise;
      }
      return Promise.resolve({
        tokens_used: 42,
        context_window_size: 1000,
        usage_ratio: 0.042,
        compaction_count: 0,
        last_compacted_at: null,
        multi_turn_memory: true,
        token_breakdown: { system_prompt: 10, replay: 20, tools: 12 },
      });
    });

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("selected-session-id")).toHaveTextContent(
        "session-1"
      )
    );

    // Switch to session-2 before session-1's context metadata resolves
    fireEvent.click(screen.getByRole("button", { name: /second session/i }));

    await waitFor(() =>
      expect(screen.getByTestId("selected-session-id")).toHaveTextContent(
        "session-2"
      )
    );
    await waitFor(() =>
      expect(api.getContextMetadata).toHaveBeenCalledWith("session-2")
    );
    await waitFor(() =>
      expect(screen.getByTestId("context-tokens")).toHaveTextContent("42")
    );

    // Resolve session-1 context after session-2 is already active
    resolveSession1Context({
      tokens_used: 9999,
      context_window_size: 1000,
      usage_ratio: 0.9999,
      compaction_count: 0,
      last_compacted_at: null,
      multi_turn_memory: true,
      token_breakdown: { system_prompt: 10, replay: 20, tools: 12 },
    });

    // Context tokens must remain 42 (session-2), not 9999 (session-1)
    expect(screen.getByTestId("context-tokens")).toHaveTextContent("42");
  });
});
