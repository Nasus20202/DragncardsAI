import { describe, expect, it } from "vitest";

import {
  applyReasoningToGatewayOptions,
  buildDraftFromSession,
  parseCustomMcps,
  parseJsonObject,
} from "@/features/play/lib/session-draft";
import { DashboardConfig, SessionDetail } from "@/features/shared/lib/types";

const config: DashboardConfig = {
  appName: "demo",
  defaultProviderId: "openai",
  defaultModelName: "gpt-4o-mini",
  defaultGameServiceMcpEnabled: true,
  defaultGameServiceMcpName: "game-service",
  defaultGameServiceMcpTransport: "streamable-http",
  defaultGameServiceMcpUrl: "http://game-service:8000/mcp/",
  defaultSkills: ["demo-skill"],
  defaultCustomMcps: [],
  dragncardsFrontendUrl: "http://localhost:4000",
  bifrostUiUrl: "http://localhost:4003",
  defaultReasoningEnabled: false,
  defaultReasoningEffort: "medium",
};

const session: SessionDetail = {
  id: "session-1",
  name: "Saved session",
  status: "active",
  context_recent_message_limit: 6,
  context_recent_tool_exchange_limit: 2,
  metadata: {},
  created_at: "2026-05-11T00:00:00Z",
  updated_at: "2026-05-11T00:00:00Z",
  terminated_at: null,
  model_config: {
    provider_id: "anthropic",
    model_name: "claude-3-5-haiku",
    gateway_options: { reasoning: { effort: "high", max_tokens: 512 } },
    provider_options: { temperature: 0.2 },
    updated_at: "2026-05-11T00:00:00Z",
  },
  skills: [
    {
      id: "skill-1",
      skill_name: "custom-skill",
      skill_path: "/skills/custom",
      created_at: "2026-05-11T00:00:00Z",
    },
  ],
  mcps: [
    {
      name: "game-service",
      transport: "streamable-http",
      server_url: "http://game-service:8000/mcp/",
      headers: {},
      enabled: true,
    },
    {
      name: "custom",
      transport: "stdio",
      server_url: "http://custom",
      headers: { authorization: "Bearer token" },
      enabled: true,
    },
  ],
  recent_job: null,
  recent_jobs: [],
};

describe("session draft helper branches", () => {
  it("builds a draft from an existing session", () => {
    const draft = buildDraftFromSession(config, session);

    expect(draft.name).toBe("Saved session");
    expect(draft.providerId).toBe("anthropic");
    expect(draft.modelName).toBe("claude-3-5-haiku");
    expect(draft.reasoning).toEqual({
      enabled: true,
      effort: "high",
      maxTokens: "512",
    });
    expect(draft.recentMessageLimit).toBe("6");
    expect(draft.recentToolExchangeLimit).toBe("2");
    expect(draft.selectedSkills).toEqual(["custom-skill"]);
  });

  it("reads the session's mode, defaulting to chat when it reports none", () => {
    expect(buildDraftFromSession(config, session).sessionMode).toBe("chat");
    expect(
      buildDraftFromSession(config, {
        ...session,
        session_mode: "orchestrated",
      }).sessionMode
    ).toBe("orchestrated");
  });

  it("treats normalized default MCP urls as the same assignment", () => {
    const draft = buildDraftFromSession(
      {
        ...config,
        defaultGameServiceMcpUrl: "http://game-service:8000/mcp",
      },
      session
    );

    expect(draft.recentMessageLimit).toBe("6");
  });

  it("rejects invalid json object input", () => {
    expect(() => parseJsonObject("[]", "Gateway options")).toThrow(
      "Gateway options must be a JSON object"
    );
    expect(() => parseJsonObject("{", "Gateway options")).toThrow(
      "Gateway options must be valid JSON"
    );
  });

  it("parses and validates custom MCP json", () => {
    expect(
      parseCustomMcps(
        '[{"name":"demo","transport":"stdio","server_url":"http://demo"}]'
      )
    ).toEqual([
      { name: "demo", transport: "stdio", server_url: "http://demo" },
    ]);
    expect(() => parseCustomMcps("{}")).toThrow(
      "Custom MCPs must be a JSON array"
    );
    expect(() => parseCustomMcps("{")).toThrow(
      "Custom MCPs must be valid JSON"
    );
  });

  it("rejects invalid reasoning max tokens", () => {
    expect(() =>
      applyReasoningToGatewayOptions(
        {},
        { enabled: true, effort: "medium", maxTokens: "0" }
      )
    ).toThrow("Reasoning max tokens must be a positive integer");

    expect(() =>
      applyReasoningToGatewayOptions(
        {},
        { enabled: true, effort: "medium", maxTokens: "3.5" }
      )
    ).toThrow("Reasoning max tokens must be a positive integer");
  });

  it("returns disabled reasoning when session has no reasoning config", () => {
    const sessionWithoutReasoning: SessionDetail = {
      ...session,
      model_config: {
        provider_id: session.model_config!.provider_id,
        model_name: session.model_config!.model_name,
        gateway_options: {},
        provider_options: session.model_config!.provider_options,
        updated_at: session.model_config!.updated_at,
      },
    };

    const draft = buildDraftFromSession(config, sessionWithoutReasoning);

    expect(draft.reasoning).toEqual({
      enabled: false,
      effort: "medium",
      maxTokens: "",
    });
  });
});
