import { describe, expect, it } from "vitest";

import {
  assemblePlayerAgentConfig,
  buildDraftFromPlayerConfig,
  createDefaultPlayerAgentDraft,
  createDefaultRoster,
  describePlayerAgentDraft,
  isPlayerSeat,
} from "@/features/play/lib/player-agents";
import { PlayerConfigResponse } from "@/features/shared/lib/types";

function makeConfig(
  overrides: Partial<PlayerConfigResponse> = {}
): PlayerConfigResponse {
  return {
    player_id: "player1",
    display_name: null,
    provider_id: null,
    model_name: null,
    reasoning: null,
    skills: null,
    gateway_options: {},
    provider_options: {},
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("player seats", () => {
  it("accepts the four Marvel Champions seats only", () => {
    expect(isPlayerSeat("player1")).toBe(true);
    expect(isPlayerSeat("player4")).toBe(true);
    expect(isPlayerSeat("player5")).toBe(false);
    expect(isPlayerSeat("villain")).toBe(false);
  });

  it("defaults to a two-seat roster", () => {
    expect(createDefaultRoster().map((d) => d.playerId)).toEqual([
      "player1",
      "player2",
    ]);
  });

  it("clamps a roster request to the supported seat range", () => {
    expect(createDefaultRoster(0)).toHaveLength(1);
    expect(createDefaultRoster(9)).toHaveLength(4);
  });
});

describe("assemblePlayerAgentConfig", () => {
  it("omits unset fields so the server applies inheritance", () => {
    const body = assemblePlayerAgentConfig(
      createDefaultPlayerAgentDraft("player1")
    );

    expect(body.provider_id).toBeUndefined();
    expect(body.model_name).toBeUndefined();
    expect(body.display_name).toBeUndefined();
    expect(body.skills).toBeUndefined();
    expect(body.persona).toBeUndefined();
  });

  it("sends reasoning disabled explicitly rather than omitting it", () => {
    const body = assemblePlayerAgentConfig(
      createDefaultPlayerAgentDraft("player1")
    );

    expect(body.reasoning).toEqual({ enabled: false });
  });

  it("sends the set fields", () => {
    const draft = {
      ...createDefaultPlayerAgentDraft("player2"),
      displayName: "  Captain Marvel  ",
      providerId: "openai",
      modelName: "gpt-4o-mini",
      reasoningEnabled: true,
      reasoningEffort: "high" as const,
      reasoningMaxTokens: "2048",
      persona: " rules-lawyer ",
      selectedSkills: ["marvel-champions-learn-to-play"],
    };

    expect(assemblePlayerAgentConfig(draft)).toEqual({
      display_name: "Captain Marvel",
      provider_id: "openai",
      model_name: "gpt-4o-mini",
      reasoning: { enabled: true, effort: "high", max_tokens: 2048 },
      persona: "rules-lawyer",
      skills: ["marvel-champions-learn-to-play"],
    });
  });

  it("ignores a non-positive or non-integer max tokens", () => {
    const base = {
      ...createDefaultPlayerAgentDraft("player1"),
      reasoningEnabled: true,
    };

    expect(
      assemblePlayerAgentConfig({ ...base, reasoningMaxTokens: "0" }).reasoning
    ).toEqual({ enabled: true, effort: "medium" });
    expect(
      assemblePlayerAgentConfig({ ...base, reasoningMaxTokens: "1.5" })
        .reasoning
    ).toEqual({ enabled: true, effort: "medium" });
  });

  it("sends an empty skill list as an explicit override", () => {
    const draft = {
      ...createDefaultPlayerAgentDraft("player1"),
      selectedSkills: [],
    };

    expect(assemblePlayerAgentConfig(draft).skills).toEqual([]);
  });
});

describe("buildDraftFromPlayerConfig", () => {
  it("round-trips an inherited seat", () => {
    const draft = buildDraftFromPlayerConfig(makeConfig());

    expect(draft).toEqual(createDefaultPlayerAgentDraft("player1"));
  });

  it("round-trips a fully specified seat", () => {
    const draft = buildDraftFromPlayerConfig(
      makeConfig({
        player_id: "player2",
        display_name: "Spider-Man",
        provider_id: "gemini",
        model_name: "gemini-2.0-flash",
        reasoning: { effort: "low", max_tokens: 512 },
        persona: "rules-lawyer",
        skills: ["a", "b"],
      })
    );

    expect(draft).toEqual({
      playerId: "player2",
      displayName: "Spider-Man",
      providerId: "gemini",
      modelName: "gemini-2.0-flash",
      reasoningEnabled: true,
      reasoningEffort: "low",
      reasoningMaxTokens: "512",
      persona: "rules-lawyer",
      selectedSkills: ["a", "b"],
    });
  });

  it("reads a seat that names no persona as naming none", () => {
    expect(buildDraftFromPlayerConfig(makeConfig()).persona).toBe("");
    expect(
      buildDraftFromPlayerConfig(makeConfig({ persona: null })).persona
    ).toBe("");
  });

  it("falls back to a medium effort for an unrecognised value", () => {
    const draft = buildDraftFromPlayerConfig(
      makeConfig({ reasoning: { effort: "extreme" } })
    );

    expect(draft.reasoningEnabled).toBe(true);
    expect(draft.reasoningEffort).toBe("medium");
  });
});

describe("describePlayerAgentDraft", () => {
  it("names inherited values rather than resolving them client-side", () => {
    expect(
      describePlayerAgentDraft(createDefaultPlayerAgentDraft("player1"))
    ).toBe(
      "inherited provider / inherited model / no reasoning / inherited skills"
    );
  });

  it("summarises an overridden seat", () => {
    const draft = {
      ...createDefaultPlayerAgentDraft("player2"),
      providerId: "openai",
      modelName: "gpt-4o-mini",
      reasoningEnabled: true,
      reasoningEffort: "high" as const,
      selectedSkills: ["a"],
    };

    expect(describePlayerAgentDraft(draft)).toBe(
      "openai / gpt-4o-mini / reasoning high / 1 skill(s)"
    );
  });
});
