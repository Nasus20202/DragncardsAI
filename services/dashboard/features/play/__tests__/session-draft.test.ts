import { describe, expect, it } from "vitest";

import {
  applyReasoningToGatewayOptions,
  buildDragnCardsRoomUrl,
  createDefaultDraft,
  parseJsonObject,
} from "@/features/play/lib/session-draft";

describe("session draft helpers", () => {
  it("builds a room url from room slug metadata", () => {
    expect(
      buildDragnCardsRoomUrl("http://localhost:3000", {
        game_session: {
          session_id: "game-1",
          plugin_name: "marvel-champions",
          plugin_id: 1,
          room_slug: "lively-fog-1234",
          created_at: "2026-05-10T00:00:00Z",
        },
      }),
    ).toBe("http://localhost:3000/room/lively-fog-1234");
  });

  it("returns null when game metadata is missing", () => {
    expect(buildDragnCardsRoomUrl("http://localhost:3000", {})).toBeNull();
  });

  it("parses JSON object config text", () => {
    expect(parseJsonObject('{"temperature":0.2}', "Gateway options")).toEqual({
      temperature: 0.2,
    });
  });

  it("creates a draft from dashboard defaults", () => {
    const draft = createDefaultDraft({
      appName: "demo",
      dragncardsFrontendUrl: "http://localhost:3000",
      defaultProviderId: "openai",
      defaultModelName: "gpt-4o-mini",
      defaultGamePlugin: "marvel-champions",
      defaultGameServiceMcpEnabled: true,
      defaultGameServiceMcpName: "game-service",
      defaultGameServiceMcpTransport: "streamable-http",
      defaultGameServiceMcpUrl: "http://game-service:8000/mcp/",
      defaultSkills: ["demo-skill"],
      defaultCustomMcps: [],
    });

    expect(draft.providerId).toBe("openai");
    expect(draft.selectedSkills).toEqual(["demo-skill"]);
    expect(draft.enableDefaultGameServiceMcp).toBe(true);
    expect(draft.reasoning).toEqual({ enabled: false, effort: "medium", maxTokens: "" });
  });

  it("applies reasoning config to gateway options", () => {
    expect(
      applyReasoningToGatewayOptions(
        { temperature: 0.2 },
        { enabled: true, effort: "high", maxTokens: "4096" },
      ),
    ).toEqual({
      temperature: 0.2,
      reasoning: { effort: "high", max_tokens: 4096 },
    });
  });

  it("removes reasoning config when disabled", () => {
    expect(
      applyReasoningToGatewayOptions(
        { reasoning: { effort: "high", max_tokens: 4096 }, temperature: 0.2 },
        { enabled: false, effort: "medium", maxTokens: "" },
      ),
    ).toEqual({ temperature: 0.2 });
  });
});
