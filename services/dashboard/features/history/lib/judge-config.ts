import {
  clampModelToProvider,
  isWorking,
} from "@/features/play/lib/session-draft";
import {
  DashboardConfig,
  JudgeConfig,
  ProviderResponse,
} from "@/features/shared/lib/types";

/**
 * Editable judge-configuration state for the Evaluate panel. Mirrors the Play
 * config draft (provider/model/reasoning/skills) plus a custom prompt/rubric.
 * `maxTokens` is kept as a string for the text input; it is parsed on assembly.
 */
export interface JudgeDraft {
  providerId: string;
  modelName: string;
  reasoningEnabled: boolean;
  reasoningEffort: "low" | "medium" | "high";
  reasoningMaxTokens: string;
  promptOverride: string;
  selectedSkills: string[];
  /**
   * `"<skill-name>/<relative-path>.md"` reference files to hand the judge on top
   * of the selected skills' `SKILL.md`.
   */
  selectedSkillReferences: string[];
}

/**
 * Build the initial judge draft from the dashboard defaults, matching how Play
 * seeds its first session draft.
 */
export function createDefaultJudgeDraft(config: DashboardConfig): JudgeDraft {
  return {
    providerId: config.defaultProviderId,
    modelName: config.defaultModelName,
    reasoningEnabled: config.defaultReasoningEnabled,
    reasoningEffort: config.defaultReasoningEffort,
    reasoningMaxTokens: "",
    promptOverride: "",
    selectedSkills: [...config.defaultSkills],
    selectedSkillReferences: [],
  };
}

/**
 * Drop every reference whose owning skill (the segment before the first `/`) is
 * no longer selected, so deselecting a skill takes its references with it.
 */
export function pruneSkillReferences(
  selectedSkills: string[],
  selectedSkillReferences: string[]
): string[] {
  return selectedSkillReferences.filter((reference) => {
    const separator = reference.indexOf("/");
    // An entry with no owning skill is malformed; drop it rather than guess.
    return (
      separator > 0 && selectedSkills.includes(reference.slice(0, separator))
    );
  });
}

/**
 * Models offered by the currently-selected provider, falling back to the
 * drafted model name when the provider is unknown / exposes none.
 */
export function modelOptionsForProvider(
  providers: ProviderResponse[],
  providerId: string,
  fallbackModel: string
): string[] {
  const provider = providers.find((p) => p.provider_id === providerId);
  if (provider && provider.models.length > 0) {
    return provider.models;
  }
  return fallbackModel ? [fallbackModel] : [];
}

/**
 * Reconcile the draft provider/model against the available providers, the same
 * way Play clamps a carried draft: prefer the drafted provider when working,
 * else the first working provider; clamp the model to the provider's offered
 * models. Returns the (possibly adjusted) provider/model.
 */
export function reconcileProviderModel(
  providers: ProviderResponse[],
  providerId: string,
  modelName: string
): { providerId: string; modelName: string } {
  if (providers.length === 0) {
    return { providerId, modelName };
  }
  const drafted = providers.find((p) => p.provider_id === providerId);
  if (drafted && isWorking(drafted)) {
    return {
      providerId: drafted.provider_id,
      modelName: clampModelToProvider(drafted, modelName),
    };
  }
  const working = providers.find(isWorking);
  if (working) {
    return { providerId: working.provider_id, modelName: working.models[0] };
  }
  return { providerId, modelName };
}

/**
 * Assemble the request `judge` object from a draft, OMITTING empty fields.
 * Returns `undefined` when nothing has been configured so the caller can drop
 * the `judge` key entirely and let the server apply its defaults.
 */
export function assembleJudgeConfig(
  draft: JudgeDraft
): JudgeConfig | undefined {
  const judge: JudgeConfig = {};

  const providerId = draft.providerId.trim();
  if (providerId) {
    judge.provider_id = providerId;
  }
  const modelName = draft.modelName.trim();
  if (modelName) {
    judge.model_name = modelName;
  }

  if (draft.reasoningEnabled) {
    judge.reasoning = { enabled: true, effort: draft.reasoningEffort };
    const maxTokens = draft.reasoningMaxTokens.trim();
    if (maxTokens) {
      const parsed = Number(maxTokens);
      if (Number.isInteger(parsed) && parsed > 0) {
        judge.reasoning.max_tokens = parsed;
      }
    }
  }

  const prompt = draft.promptOverride.trim();
  if (prompt) {
    judge.prompt_override = prompt;
  }

  if (draft.selectedSkills.length > 0) {
    judge.skills = [...draft.selectedSkills];
  }

  if (draft.selectedSkillReferences.length > 0) {
    judge.skill_references = [...draft.selectedSkillReferences];
  }

  return Object.keys(judge).length > 0 ? judge : undefined;
}
