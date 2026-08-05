import { describe, expect, it } from "vitest";

import {
  MAX_PERSONA_PROMPT_CHARS,
  PersonaDraft,
  assemblePersonaRequest,
  buildDraftFromPersona,
  createEmptyPersonaDraft,
  describePersona,
  describePersonaDraftProblem,
  describePersonaDraftProblems,
  formatAllowedTools,
  parseAllowedTools,
} from "@/features/personas/lib/personas";
import { PersonaResponse } from "@/features/shared/lib/types";

function persona(overrides: Partial<PersonaResponse> = {}): PersonaResponse {
  return {
    name: "rules-lawyer",
    display_name: "Rules Lawyer",
    description: "Checks rule interactions.",
    system_prompt: "Answer only from the printed rules.",
    provider_id: null,
    model_name: null,
    reasoning: null,
    skills: null,
    allowed_tools: null,
    gateway_options: {},
    provider_options: {},
    created_at: "2026-07-28T00:00:00Z",
    updated_at: "2026-07-28T00:00:00Z",
    ...overrides,
  };
}

function draft(overrides: Partial<PersonaDraft> = {}): PersonaDraft {
  return {
    ...createEmptyPersonaDraft(),
    name: "rules-lawyer",
    systemPrompt: "Answer only from the printed rules.",
    ...overrides,
  };
}

describe("buildDraftFromPersona", () => {
  it("reads inherit-meaning nulls back as empty or null", () => {
    const hydrated = buildDraftFromPersona(persona());

    expect(hydrated.providerId).toBe("");
    expect(hydrated.modelName).toBe("");
    expect(hydrated.selectedSkills).toBeNull();
    expect(hydrated.allowedTools).toBeNull();
    expect(hydrated.reasoningEnabled).toBe(false);
  });

  it("hydrates set values, including an empty allowlist", () => {
    const hydrated = buildDraftFromPersona(
      persona({
        provider_id: "openai",
        model_name: "gpt-4o-mini",
        reasoning: { effort: "high", max_tokens: 2048 },
        skills: ["demo-skill"],
        allowed_tools: [],
      })
    );

    expect(hydrated.providerId).toBe("openai");
    expect(hydrated.modelName).toBe("gpt-4o-mini");
    expect(hydrated.reasoningEnabled).toBe(true);
    expect(hydrated.reasoningEffort).toBe("high");
    expect(hydrated.reasoningMaxTokens).toBe("2048");
    expect(hydrated.selectedSkills).toEqual(["demo-skill"]);
    // An empty allowlist is not the same as no allowlist: it means no MCP tools.
    expect(hydrated.allowedTools).toEqual([]);
  });
});

describe("assemblePersonaRequest", () => {
  it("omits unset fields so the server applies inheritance", () => {
    const body = assemblePersonaRequest(draft());

    expect(body).toEqual({
      system_prompt: "Answer only from the printed rules.",
      reasoning: { enabled: false },
    });
    expect(body.provider_id).toBeUndefined();
    expect(body.skills).toBeUndefined();
    expect(body.allowed_tools).toBeUndefined();
  });

  it("sends set fields, an empty skill list, and an empty allowlist", () => {
    const body = assemblePersonaRequest(
      draft({
        displayName: " Rules Lawyer ",
        description: " Checks rules. ",
        providerId: "openai",
        modelName: "gpt-4o-mini",
        reasoningEnabled: true,
        reasoningEffort: "high",
        reasoningMaxTokens: "2048",
        selectedSkills: [],
        allowedTools: [],
      })
    );

    expect(body.display_name).toBe("Rules Lawyer");
    expect(body.description).toBe("Checks rules.");
    expect(body.provider_id).toBe("openai");
    expect(body.model_name).toBe("gpt-4o-mini");
    expect(body.reasoning).toEqual({
      enabled: true,
      effort: "high",
      max_tokens: 2048,
    });
    expect(body.skills).toEqual([]);
    expect(body.allowed_tools).toEqual([]);
  });

  it("drops a non-positive reasoning token count rather than sending it", () => {
    const body = assemblePersonaRequest(
      draft({ reasoningEnabled: true, reasoningMaxTokens: "0" })
    );

    expect(body.reasoning).toEqual({ enabled: true, effort: "medium" });
  });
});

describe("describePersonaDraftProblem", () => {
  it("accepts a named persona with a prompt", () => {
    expect(describePersonaDraftProblem(draft())).toBeNull();
  });

  it("requires a name", () => {
    expect(describePersonaDraftProblem(draft({ name: "  " }))).toMatch(/name/i);
  });

  it("requires the name to be a lowercase slug", () => {
    expect(
      describePersonaDraftProblem(draft({ name: "Rules Lawyer" }))
    ).toMatch(/lowercase/i);
  });

  it("requires a system prompt", () => {
    expect(describePersonaDraftProblem(draft({ systemPrompt: " " }))).toMatch(
      /prompt/i
    );
  });

  it("rejects a prompt over the orchestrator's limit", () => {
    const problem = describePersonaDraftProblem(
      draft({ systemPrompt: "x".repeat(MAX_PERSONA_PROMPT_CHARS + 1) })
    );

    expect(problem).toContain(String(MAX_PERSONA_PROMPT_CHARS));
  });

  it("accepts a prompt exactly at the limit", () => {
    expect(
      describePersonaDraftProblem(
        draft({ systemPrompt: "x".repeat(MAX_PERSONA_PROMPT_CHARS) })
      )
    ).toBeNull();
  });
});

describe("describePersonaDraftProblems", () => {
  it("reports no problem for a draft that can be saved", () => {
    expect(describePersonaDraftProblems(draft())).toEqual({
      name: null,
      systemPrompt: null,
    });
  });

  it("attributes a missing name to the name field", () => {
    const problems = describePersonaDraftProblems(draft({ name: "  " }));

    expect(problems.name).toMatch(/needs a name/i);
    expect(problems.systemPrompt).toBeNull();
  });

  it("attributes a malformed name to the name field", () => {
    const problems = describePersonaDraftProblems(
      draft({ name: "Rules Lawyer" })
    );

    expect(problems.name).toMatch(/lowercase/i);
    expect(problems.systemPrompt).toBeNull();
  });

  it("attributes a missing prompt to the system prompt field", () => {
    const problems = describePersonaDraftProblems(draft({ systemPrompt: " " }));

    expect(problems.name).toBeNull();
    expect(problems.systemPrompt).toMatch(/system prompt/i);
  });

  it("attributes an over-limit prompt to the system prompt field", () => {
    const problems = describePersonaDraftProblems(
      draft({ systemPrompt: "x".repeat(MAX_PERSONA_PROMPT_CHARS + 1) })
    );

    expect(problems.name).toBeNull();
    expect(problems.systemPrompt).toContain(String(MAX_PERSONA_PROMPT_CHARS));
  });

  it("states both problems rather than hiding the second behind the first", () => {
    const problems = describePersonaDraftProblems(
      draft({ name: "Rules Lawyer", systemPrompt: "" })
    );

    expect(problems.name).toMatch(/lowercase/i);
    expect(problems.systemPrompt).toMatch(/system prompt/i);
  });
});

describe("allowlist text round-trip", () => {
  it("parses names separated by newlines and commas, ignoring blanks", () => {
    expect(parseAllowedTools(" a\n b , c \n\n")).toEqual(["a", "b", "c"]);
  });

  it("parses an all-blank list as an empty allowlist, not as no allowlist", () => {
    expect(parseAllowedTools("  \n ")).toEqual([]);
  });

  it("formats no allowlist as empty text", () => {
    expect(formatAllowedTools(null)).toBe("");
    expect(formatAllowedTools(["a", "b"])).toBe("a\nb");
  });
});

describe("describePersona", () => {
  it("says inherited rather than resolving on the client", () => {
    expect(describePersona(persona())).toBe(
      "inherited provider / inherited model / inherited skills / all session tools"
    );
  });

  it("counts the skills and tools a persona pins", () => {
    expect(
      describePersona(
        persona({
          provider_id: "openai",
          model_name: "gpt-4o-mini",
          skills: ["a", "b"],
          allowed_tools: ["t"],
        })
      )
    ).toBe("openai / gpt-4o-mini / 2 skill(s) / 1 tool(s)");
  });
});
