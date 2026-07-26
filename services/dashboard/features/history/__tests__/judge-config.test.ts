import { describe, expect, it } from "vitest";

import {
  JudgeDraft,
  assembleJudgeConfig,
  createDefaultJudgeDraft,
  modelOptionsForProvider,
  reconcileProviderModel,
} from "@/features/history/lib/judge-config";
import { DashboardConfig, ProviderResponse } from "@/features/shared/lib/types";

const CONFIG: DashboardConfig = {
  appName: "Test",
  defaultProviderId: "openrouter",
  defaultModelName: "openrouter/free",
  defaultGameServiceMcpEnabled: true,
  defaultGameServiceMcpName: "game-service",
  defaultGameServiceMcpTransport: "streamable-http",
  defaultGameServiceMcpUrl: "http://localhost:4001/mcp/",
  defaultSkills: ["core-rules"],
  defaultCustomMcps: [],
  dragncardsFrontendUrl: "http://localhost:3000",
  defaultReasoningEnabled: true,
  defaultReasoningEffort: "medium",
};

function draft(overrides: Partial<JudgeDraft> = {}): JudgeDraft {
  return {
    providerId: "openrouter",
    modelName: "openrouter/free",
    reasoningEnabled: false,
    reasoningEffort: "medium",
    reasoningMaxTokens: "",
    promptOverride: "",
    selectedSkills: [],
    ...overrides,
  };
}

describe("createDefaultJudgeDraft", () => {
  it("seeds from the dashboard defaults", () => {
    expect(createDefaultJudgeDraft(CONFIG)).toEqual({
      providerId: "openrouter",
      modelName: "openrouter/free",
      reasoningEnabled: true,
      reasoningEffort: "medium",
      reasoningMaxTokens: "",
      promptOverride: "",
      selectedSkills: ["core-rules"],
    });
  });
});

describe("assembleJudgeConfig", () => {
  it("includes provider/model but omits empty optional fields", () => {
    expect(assembleJudgeConfig(draft())).toEqual({
      provider_id: "openrouter",
      model_name: "openrouter/free",
    });
  });

  it("assembles reasoning, prompt, and skills when set", () => {
    const result = assembleJudgeConfig(
      draft({
        reasoningEnabled: true,
        reasoningEffort: "high",
        reasoningMaxTokens: "4096",
        promptOverride: "  custom rubric  ",
        selectedSkills: ["a", "b"],
      })
    );
    expect(result).toEqual({
      provider_id: "openrouter",
      model_name: "openrouter/free",
      reasoning: { enabled: true, effort: "high", max_tokens: 4096 },
      prompt_override: "custom rubric",
      skills: ["a", "b"],
    });
  });

  it("omits max_tokens when blank or non-positive and omits reasoning when disabled", () => {
    const enabledNoTokens = assembleJudgeConfig(
      draft({ reasoningEnabled: true, reasoningMaxTokens: "0" })
    );
    expect(enabledNoTokens?.reasoning).toEqual({
      enabled: true,
      effort: "medium",
    });

    const disabled = assembleJudgeConfig(
      draft({ reasoningEnabled: false, reasoningMaxTokens: "4096" })
    );
    expect(disabled?.reasoning).toBeUndefined();
  });

  it("returns undefined when nothing is configured", () => {
    expect(
      assembleJudgeConfig(draft({ providerId: " ", modelName: "" }))
    ).toBeUndefined();
  });
});

describe("modelOptionsForProvider", () => {
  const providers: ProviderResponse[] = [
    {
      provider_id: "openrouter",
      model_prefix: "openrouter/",
      models: ["m1", "m2"],
      available: true,
      error: null,
    },
  ];

  it("returns the provider's models", () => {
    expect(modelOptionsForProvider(providers, "openrouter", "x")).toEqual([
      "m1",
      "m2",
    ]);
  });

  it("falls back to the drafted model for an unknown provider", () => {
    expect(modelOptionsForProvider(providers, "ghost", "fallback")).toEqual([
      "fallback",
    ]);
  });
});

describe("reconcileProviderModel", () => {
  const providers: ProviderResponse[] = [
    {
      provider_id: "openrouter",
      model_prefix: "openrouter/",
      models: ["m1", "m2"],
      available: true,
      error: null,
    },
    {
      provider_id: "broken",
      model_prefix: "broken/",
      models: [],
      available: false,
      error: "down",
    },
  ];

  it("keeps the drafted provider and clamps a stale model", () => {
    expect(reconcileProviderModel(providers, "openrouter", "stale")).toEqual({
      providerId: "openrouter",
      modelName: "m1",
    });
  });

  it("falls back to the first working provider when the drafted one is broken", () => {
    expect(reconcileProviderModel(providers, "broken", "x")).toEqual({
      providerId: "openrouter",
      modelName: "m1",
    });
  });

  it("returns the draft unchanged when no providers are loaded", () => {
    expect(reconcileProviderModel([], "p", "m")).toEqual({
      providerId: "p",
      modelName: "m",
    });
  });
});
