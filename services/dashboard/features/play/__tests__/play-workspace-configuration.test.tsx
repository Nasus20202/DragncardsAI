import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import {
  baseConfig,
  getApi,
  renderPlayWorkspace,
  resetPlayWorkspaceEnvironment,
  sessionDetail,
  sessionSummary,
} from "@/features/play/__tests__/play-workspace-test-support";

const api = getApi();

describe("PlayWorkspace configuration", () => {
  beforeEach(() => {
    resetPlayWorkspaceEnvironment();
  });

  it("syncs model config when the draft provider changes", async () => {
    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("selected-session-name")).toHaveTextContent(
        "Existing session"
      )
    );
    fireEvent.click(screen.getByRole("button", { name: /change provider/i }));

    await waitFor(() => {
      expect(api.setModelConfig).toHaveBeenCalledWith(
        "session-1",
        expect.objectContaining({
          provider_id: "anthropic",
          model_name: "claude-3-5-haiku",
        })
      );
    });
  });

  it("creates a session, selects it, and persists the selection", async () => {
    api.listSessions
      .mockResolvedValueOnce([sessionSummary])
      .mockResolvedValueOnce([
        { ...sessionSummary, id: "session-2", name: "Created" },
      ]);

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("selected-session-id")).toHaveTextContent(
        "session-1"
      )
    );
    fireEvent.click(screen.getByRole("button", { name: /create session/i }));

    await waitFor(() =>
      expect(api.createSession).toHaveBeenCalledWith(expect.any(String), {
        context_recent_message_limit: null,
        context_recent_tool_exchange_limit: null,
      })
    );
    await waitFor(() =>
      expect(globalThis.localStorage.getItem("play:selectedSessionId")).toBe(
        "session-2"
      )
    );
    expect(window.location.search).toBe("?session=session-2");
  });

  it("creates a new session seeded with the last-used session settings", async () => {
    api.fetchDashboardConfig.mockResolvedValueOnce({
      ...baseConfig,
      defaultProviderId: "lmstudio",
      defaultModelName: "qwen3.5-0.8b",
      defaultSkills: ["skill-b"],
    });
    api.getSession.mockResolvedValueOnce({
      ...sessionDetail,
      model_config: {
        provider_id: "openai",
        model_name: "openai/babbage-002",
        gateway_options: { existing: true },
        provider_options: { temperature: 0 },
        updated_at: "2026-05-11T00:00:00Z",
      },
      skills: [
        {
          id: "skill-existing",
          skill_name: "dragncards",
          skill_path: "/skills/dragncards",
          created_at: "2026-05-11T00:00:00Z",
        },
      ],
      mcps: [],
    });
    api.listSessions
      .mockResolvedValueOnce([sessionSummary])
      .mockResolvedValueOnce([
        { ...sessionSummary, id: "session-2", name: "Created" },
      ]);

    renderPlayWorkspace();

    // Wait until the selected session's draft has fully loaded before creating
    // a new one, so the new session is seeded from the last-used settings.
    await waitFor(() =>
      expect(screen.getByTestId("selected-session-name")).toHaveTextContent(
        "Existing session"
      )
    );
    await waitFor(() =>
      expect(screen.getByTestId("selected-session-id")).toHaveTextContent(
        "session-1"
      )
    );

    fireEvent.click(screen.getByRole("button", { name: /create session/i }));

    await waitFor(() =>
      expect(api.setModelConfig).toHaveBeenCalledWith(
        "session-2",
        expect.objectContaining({
          // Provider and advanced options are carried forward; the model is
          // normalized to a valid model for the provider.
          provider_id: "openai",
          model_name: "gpt-4o-mini",
          gateway_options: { existing: true },
          provider_options: { temperature: 0 },
        })
      )
    );
    // The previously selected session's skill is carried forward, not the
    // configuration default skill.
    expect(api.addSkill).toHaveBeenCalledWith("session-2", "dragncards");
    expect(api.addSkill).not.toHaveBeenCalledWith("session-2", "skill-b");
    // MCPs are now managed via McpSection UI, not automatically from config
    expect(api.addMcp).not.toHaveBeenCalled();
  });

  it("saves replay window settings with the session update", async () => {
    api.getSession.mockResolvedValueOnce({
      ...sessionDetail,
      context_recent_message_limit: 5,
      context_recent_tool_exchange_limit: 2,
    });

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("selected-session-name")).toHaveTextContent(
        "Existing session"
      )
    );

    fireEvent.click(
      screen.getByRole("button", { name: /save configuration/i })
    );

    await waitFor(() =>
      expect(api.updateSession).toHaveBeenCalledWith(
        "session-1",
        expect.objectContaining({
          context_recent_message_limit: 5,
          context_recent_tool_exchange_limit: 2,
        })
      )
    );
  });

  it("keeps disabled MCPs visible after saving configuration", async () => {
    api.listSessionMcps
      .mockResolvedValueOnce([
        {
          name: "game-service",
          transport: "streamable-http",
          server_url: "http://game-service:8000/mcp/",
          enabled: false,
        },
      ])
      .mockResolvedValueOnce([
        {
          name: "game-service",
          transport: "streamable-http",
          server_url: "http://game-service:8000/mcp/",
          enabled: false,
        },
      ]);

    renderPlayWorkspace();

    await waitFor(() =>
      expect(
        screen.getByTestId("selected-session-mcp-count")
      ).toHaveTextContent("1")
    );

    fireEvent.click(
      screen.getByRole("button", { name: /save configuration/i })
    );

    await waitFor(() => expect(api.listSessionMcps).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId("selected-session-mcp-count")).toHaveTextContent(
      "1"
    );
  });
});
