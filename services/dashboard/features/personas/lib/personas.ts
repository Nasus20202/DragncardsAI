import { PersonaRequest, PersonaResponse } from "@/features/shared/lib/types";

/**
 * The orchestrator's own bound on a persona's system prompt
 * (`MAX_PERSONA_PROMPT_CHARS`). Mirrored here so the editor can show the limit
 * while the user types instead of surfacing it only as a rejected save.
 */
export const MAX_PERSONA_PROMPT_CHARS = 8000;

/** The orchestrator's persona-name rule: a lowercase slug, at most 64 characters. */
export const PERSONA_NAME_PATTERN = /^[a-z0-9][a-z0-9-]{0,63}$/;

/**
 * Editable persona state. Every field is a string or a flag so it maps directly
 * onto a form control, and an empty string means "inherit from the session that
 * spawns the subagent" — the same meaning the stored `null` carries.
 */
export interface PersonaDraft {
  name: string;
  displayName: string;
  description: string;
  systemPrompt: string;
  providerId: string;
  modelName: string;
  reasoningEnabled: boolean;
  reasoningEffort: "low" | "medium" | "high";
  reasoningMaxTokens: string;
  /** `null` inherits the spawning session's skills; an array replaces them. */
  selectedSkills: string[] | null;
  /**
   * `null` narrows nothing. An array is an allowlist that can only REMOVE tools
   * from what the child session already exposes — a persona can never widen
   * tool access.
   */
  allowedTools: string[] | null;
}

export function createEmptyPersonaDraft(): PersonaDraft {
  return {
    name: "",
    displayName: "",
    description: "",
    systemPrompt: "",
    providerId: "",
    modelName: "",
    reasoningEnabled: false,
    reasoningEffort: "medium",
    reasoningMaxTokens: "",
    selectedSkills: null,
    allowedTools: null,
  };
}

export function buildDraftFromPersona(persona: PersonaResponse): PersonaDraft {
  const effort = persona.reasoning?.effort;
  return {
    name: persona.name,
    displayName: persona.display_name ?? "",
    description: persona.description ?? "",
    systemPrompt: persona.system_prompt,
    providerId: persona.provider_id ?? "",
    modelName: persona.model_name ?? "",
    reasoningEnabled: persona.reasoning !== null,
    reasoningEffort:
      effort === "low" || effort === "high" || effort === "medium"
        ? effort
        : "medium",
    reasoningMaxTokens:
      persona.reasoning?.max_tokens === undefined
        ? ""
        : String(persona.reasoning.max_tokens),
    selectedSkills: persona.skills === null ? null : [...persona.skills],
    allowedTools:
      persona.allowed_tools === null ? null : [...persona.allowed_tools],
  };
}

/**
 * Assemble the request body, OMITTING unset fields so the orchestrator applies
 * inheritance rather than us freezing a session's current values into the
 * persona. `reasoning` is always sent, because "reasoning off" has to be
 * expressible and not merely absent.
 */
export function assemblePersonaRequest(draft: PersonaDraft): PersonaRequest {
  const body: PersonaRequest = { system_prompt: draft.systemPrompt };

  const displayName = draft.displayName.trim();
  if (displayName) {
    body.display_name = displayName;
  }
  const description = draft.description.trim();
  if (description) {
    body.description = description;
  }
  const providerId = draft.providerId.trim();
  if (providerId) {
    body.provider_id = providerId;
  }
  const modelName = draft.modelName.trim();
  if (modelName) {
    body.model_name = modelName;
  }

  if (draft.reasoningEnabled) {
    body.reasoning = { enabled: true, effort: draft.reasoningEffort };
    const maxTokens = draft.reasoningMaxTokens.trim();
    if (maxTokens) {
      const parsed = Number(maxTokens);
      if (Number.isInteger(parsed) && parsed > 0) {
        body.reasoning.max_tokens = parsed;
      }
    }
  } else {
    body.reasoning = { enabled: false };
  }

  if (draft.selectedSkills !== null) {
    body.skills = [...draft.selectedSkills];
  }
  if (draft.allowedTools !== null) {
    body.allowed_tools = [...draft.allowedTools];
  }

  return body;
}

/**
 * Why each validated field of a draft cannot be saved, `null` per field when it
 * can. Reported per field rather than as one first-problem string so the editor
 * can state a problem next to the control that causes it, and so a draft with
 * two problems states both instead of hiding the second behind the first.
 */
export interface PersonaDraftProblems {
  name: string | null;
  systemPrompt: string | null;
}

/** The order `describePersonaDraftProblem` reports a draft's problems in. */
const PROBLEM_ORDER: (keyof PersonaDraftProblems)[] = ["name", "systemPrompt"];

export function describePersonaDraftProblems(
  draft: PersonaDraft
): PersonaDraftProblems {
  const name = draft.name.trim();
  let nameProblem: string | null = null;
  if (!name) {
    nameProblem = "A persona needs a name.";
  } else if (!PERSONA_NAME_PATTERN.test(name)) {
    nameProblem =
      "A persona name must be lowercase letters, digits and hyphens, starting with a letter or digit.";
  }

  let systemPromptProblem: string | null = null;
  if (!draft.systemPrompt.trim()) {
    systemPromptProblem =
      "A persona needs a system prompt — that is what makes it a persona.";
  } else if (draft.systemPrompt.length > MAX_PERSONA_PROMPT_CHARS) {
    systemPromptProblem = `The system prompt is ${draft.systemPrompt.length} characters, over the ${MAX_PERSONA_PROMPT_CHARS} limit.`;
  }

  return { name: nameProblem, systemPrompt: systemPromptProblem };
}

/**
 * Why this draft cannot be saved, or `null` when it can. Checked in the browser
 * so the orchestrator's bounds are visible before the request, not only in the
 * error it returns. Derived from the per-field problems so there is one place
 * that decides what makes a draft invalid.
 */
export function describePersonaDraftProblem(
  draft: PersonaDraft
): string | null {
  const problems = describePersonaDraftProblems(draft);
  for (const field of PROBLEM_ORDER) {
    if (problems[field] !== null) {
      return problems[field];
    }
  }
  return null;
}

/**
 * Parse the comma or newline separated tool allowlist the editor takes as text.
 * An empty entry list is a real value — it means the persona gets no MCP tools.
 */
export function parseAllowedTools(text: string): string[] {
  return text
    .split(/[\n,]/)
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);
}

export function formatAllowedTools(allowedTools: string[] | null): string {
  return allowedTools === null ? "" : allowedTools.join("\n");
}

/** A one-line summary of what a persona will run with, for the list. */
export function describePersona(persona: PersonaResponse): string {
  const model = persona.model_name ?? "inherited model";
  const provider = persona.provider_id ?? "inherited provider";
  const skills =
    persona.skills === null
      ? "inherited skills"
      : `${persona.skills.length} skill(s)`;
  const tools =
    persona.allowed_tools === null
      ? "all session tools"
      : `${persona.allowed_tools.length} tool(s)`;
  return `${provider} / ${model} / ${skills} / ${tools}`;
}
