import { describe, expect, it } from "vitest";

import {
  applyReasoningToGatewayOptions,
  createDefaultDraft,
  createNewSessionDraft,
  parseOptionalPositiveInteger,
  parseJsonObject,
} from "@/features/play/lib/session-draft";
import {
  DashboardConfig,
  ProviderResponse,
  SessionDraft,
} from "@/features/shared/lib/types";

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

function provider(
  overrides: Partial<ProviderResponse> & Pick<ProviderResponse, "provider_id">
): ProviderResponse {
  return {
    model_prefix: overrides.provider_id,
    models: [],
    available: true,
    error: null,
    ...overrides,
  };
}

const lastUsedAnthropic: SessionDraft = {
  name: "Old session name",
  providerId: "anthropic",
  modelName: "claude-3-5",
  recentMessageLimit: "12",
  recentToolExchangeLimit: "5",
  reasoning: { enabled: true, effort: "high", maxTokens: "2048" },
  gatewayOptionsText: '{"temperature":0.3}',
  providerOptionsText: '{"foo":"bar"}',
  selectedSkills: ["skill-a", "skill-b"],
};

describe("session draft helpers", () => {
  it("parses JSON object config text", () => {
    expect(parseJsonObject('{"temperature":0.2}', "Gateway options")).toEqual({
      temperature: 0.2,
    });
  });

  it("creates a draft from dashboard defaults", () => {
    const draft = createDefaultDraft({
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
    });

    expect(draft.providerId).toBe("openai");
    expect(draft.selectedSkills).toEqual(["demo-skill"]);
    expect(draft.reasoning).toEqual({
      enabled: false,
      effort: "medium",
      maxTokens: "",
    });
  });

  it("applies reasoning config to gateway options", () => {
    expect(
      applyReasoningToGatewayOptions(
        { temperature: 0.2 },
        { enabled: true, effort: "high", maxTokens: "4096" }
      )
    ).toEqual({
      temperature: 0.2,
      reasoning: { effort: "high", max_tokens: 4096 },
    });
  });

  it("removes reasoning config when disabled", () => {
    expect(
      applyReasoningToGatewayOptions(
        { reasoning: { effort: "high", max_tokens: 4096 }, temperature: 0.2 },
        { enabled: false, effort: "medium", maxTokens: "" }
      )
    ).toEqual({ temperature: 0.2 });
  });

  it("falls back to config defaults when there is no prior draft", () => {
    const draft = createNewSessionDraft(config, null);

    expect(draft.providerId).toBe("openai");
    expect(draft.modelName).toBe("gpt-4o-mini");
    expect(draft.selectedSkills).toEqual(["demo-skill"]);
  });

  it("carries forward last-used settings into a new session draft", () => {
    const lastUsed = lastUsedAnthropic;

    const draft = createNewSessionDraft(config, lastUsed, [
      provider({ provider_id: "anthropic", models: ["claude-3-5"] }),
    ]);

    expect(draft.providerId).toBe("anthropic");
    expect(draft.modelName).toBe("claude-3-5");
    expect(draft.recentMessageLimit).toBe("12");
    expect(draft.recentToolExchangeLimit).toBe("5");
    expect(draft.reasoning).toEqual({
      enabled: true,
      effort: "high",
      maxTokens: "2048",
    });
    expect(draft.gatewayOptionsText).toBe('{"temperature":0.3}');
    expect(draft.providerOptionsText).toBe('{"foo":"bar"}');
    expect(draft.selectedSkills).toEqual(["skill-a", "skill-b"]);
    // A fresh name is always generated rather than reused.
    expect(draft.name).not.toBe("Old session name");
    // Mutating the new draft must not affect the source draft.
    draft.selectedSkills.push("skill-c");
    expect(lastUsed.selectedSkills).toEqual(["skill-a", "skill-b"]);
  });

  it("falls back to a working provider when the carried provider is unavailable", () => {
    const draft = createNewSessionDraft(config, lastUsedAnthropic, [
      provider({
        provider_id: "anthropic",
        models: ["claude-3-5"],
        available: false,
      }),
      provider({ provider_id: "openai", models: ["gpt-4o-mini"] }),
    ]);

    // The carried provider is unavailable, so the draft falls back to a working
    // provider/model rather than pinning to the broken one.
    expect(draft.providerId).toBe("openai");
    expect(draft.modelName).toBe("gpt-4o-mini");
    // Non-provider settings are still carried forward.
    expect(draft.recentMessageLimit).toBe("12");
    expect(draft.selectedSkills).toEqual(["skill-a", "skill-b"]);
  });

  it("falls back when the carried provider exposes no models", () => {
    const draft = createNewSessionDraft(config, lastUsedAnthropic, [
      provider({ provider_id: "anthropic", models: [] }),
      provider({ provider_id: "openai", models: ["gpt-4o-mini"] }),
    ]);

    expect(draft.providerId).toBe("openai");
    expect(draft.modelName).toBe("gpt-4o-mini");
  });

  it("falls back when the carried provider is missing from the list", () => {
    const draft = createNewSessionDraft(config, lastUsedAnthropic, [
      provider({ provider_id: "openai", models: ["gpt-4o-mini"] }),
    ]);

    expect(draft.providerId).toBe("openai");
    expect(draft.modelName).toBe("gpt-4o-mini");
  });

  it("treats empty and zero replay inputs as unlimited", () => {
    expect(parseOptionalPositiveInteger("", "Recent message limit")).toBeNull();
    expect(
      parseOptionalPositiveInteger("0", "Recent message limit")
    ).toBeNull();
    expect(parseOptionalPositiveInteger("3", "Recent message limit")).toBe(3);
  });
});
