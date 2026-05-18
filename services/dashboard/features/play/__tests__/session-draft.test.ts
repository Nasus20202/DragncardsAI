import { describe, expect, it } from "vitest";

import {
  applyReasoningToGatewayOptions,
  createDefaultDraft,
  parseOptionalPositiveInteger,
  parseJsonObject,
} from "@/features/play/lib/session-draft";

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

  it("treats empty and zero replay inputs as unlimited", () => {
    expect(parseOptionalPositiveInteger("", "Recent message limit")).toBeNull();
    expect(
      parseOptionalPositiveInteger("0", "Recent message limit")
    ).toBeNull();
    expect(parseOptionalPositiveInteger("3", "Recent message limit")).toBe(3);
  });
});
