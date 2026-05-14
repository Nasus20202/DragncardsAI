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
      expect(screen.getByTestId("draft-provider")).toHaveTextContent("openai")
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

  it("creates a fresh session from dashboard defaults instead of cloning the selected session draft", async () => {
    api.fetchDashboardConfig.mockResolvedValueOnce({
      ...baseConfig,
      defaultProviderId: "lmstudio",
      defaultModelName: "qwen3.5-0.8b",
      defaultSkills: ["skill-b"],
      defaultCustomMcps: [
        {
          name: "custom-mcp",
          transport: "streamable-http",
          server_url: "http://custom-mcp.test/mcp/",
          headers: { Authorization: "Bearer test" },
        },
      ],
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
      mcps: [
        {
          id: "mcp-existing",
          name: "game-service",
          transport: "streamable-http",
          server_url: "http://localhost:4001/mcp/",
          headers: {},
          created_at: "2026-05-11T00:00:00Z",
          updated_at: "2026-05-11T00:00:00Z",
        },
      ],
    });
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
      expect(api.setModelConfig).toHaveBeenCalledWith(
        "session-2",
        expect.objectContaining({
          provider_id: "lmstudio",
          model_name: "qwen3.5-0.8b",
          gateway_options: {},
          provider_options: {},
        })
      )
    );
    expect(api.addSkill).toHaveBeenCalledWith("session-2", "skill-b");
    expect(api.addMcp).toHaveBeenCalledWith(
      "session-2",
      expect.objectContaining({
        name: "game-service",
        server_url: "http://game-service:8000/mcp/",
      })
    );
    expect(api.addMcp).toHaveBeenCalledWith("session-2", {
      name: "custom-mcp",
      transport: "streamable-http",
      server_url: "http://custom-mcp.test/mcp/",
      headers: { Authorization: "Bearer test" },
    });
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
});
