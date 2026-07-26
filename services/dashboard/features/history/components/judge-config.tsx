"use client";

import {
  ProviderResponse,
  SkillDefinitionResponse,
} from "@/features/shared/lib/types";
import {
  JudgeDraft,
  modelOptionsForProvider,
} from "@/features/history/lib/judge-config";

export interface JudgeConfigPanelProps {
  draft: JudgeDraft;
  providers: ProviderResponse[];
  skills: SkillDefinitionResponse[];
  disabled?: boolean;
  onChange: (next: JudgeDraft) => void;
}

const inputClass =
  "rounded border border-default-200 bg-background px-2 py-1 text-sm text-foreground";

/**
 * Play-parity judge configuration controls for the Evaluate panel: provider +
 * model selects (sourced from listProviders), reasoning toggle/effort/max
 * tokens, a custom prompt/rubric textarea, and a skills multiselect (from
 * listAvailableSkills). All values feed {@link assembleJudgeConfig}.
 */
export function JudgeConfigPanel({
  draft,
  providers,
  skills,
  disabled = false,
  onChange,
}: JudgeConfigPanelProps) {
  const set = <K extends keyof JudgeDraft>(key: K, value: JudgeDraft[K]) =>
    onChange({ ...draft, [key]: value });

  const modelOptions = modelOptionsForProvider(
    providers,
    draft.providerId,
    draft.modelName
  );

  return (
    <fieldset
      className="flex flex-col gap-3 rounded-lg border border-default-200/60 p-3"
      data-testid="judge-config"
      aria-label="Judge configuration"
    >
      <span className="text-xs font-semibold uppercase tracking-wide text-default-400">
        Judge
      </span>

      <label className="flex flex-col gap-1 text-sm">
        <span className="text-xs text-default-500">Provider</span>
        <select
          aria-label="Judge provider"
          data-testid="judge-provider"
          className={inputClass}
          value={draft.providerId}
          disabled={disabled}
          onChange={(event) => {
            const providerId = event.target.value;
            const nextModels = modelOptionsForProvider(
              providers,
              providerId,
              draft.modelName
            );
            // Clamp the model to the newly-selected provider's offerings.
            const modelName = nextModels.includes(draft.modelName)
              ? draft.modelName
              : (nextModels[0] ?? draft.modelName);
            onChange({ ...draft, providerId, modelName });
          }}
        >
          {providers.length === 0 && (
            <option value={draft.providerId}>{draft.providerId}</option>
          )}
          {providers.map((provider) => (
            <option key={provider.provider_id} value={provider.provider_id}>
              {provider.provider_id}
              {provider.available === false ? " (unavailable)" : ""}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1 text-sm">
        <span className="text-xs text-default-500">Model</span>
        <select
          aria-label="Judge model"
          data-testid="judge-model"
          className={inputClass}
          value={draft.modelName}
          disabled={disabled || modelOptions.length === 0}
          onChange={(event) => set("modelName", event.target.value)}
        >
          {!modelOptions.includes(draft.modelName) && (
            <option value={draft.modelName}>{draft.modelName}</option>
          )}
          {modelOptions.map((model) => (
            <option key={model} value={model}>
              {model}
            </option>
          ))}
        </select>
      </label>

      <div className="flex flex-col gap-2">
        <label className="flex items-center gap-1.5 text-sm">
          <input
            type="checkbox"
            data-testid="judge-reasoning-enabled"
            checked={draft.reasoningEnabled}
            disabled={disabled}
            onChange={(event) => set("reasoningEnabled", event.target.checked)}
          />
          Reasoning
        </label>
        {draft.reasoningEnabled && (
          <div className="flex flex-wrap items-center gap-2 pl-5">
            <select
              aria-label="Reasoning effort"
              data-testid="judge-reasoning-effort"
              className={inputClass}
              value={draft.reasoningEffort}
              disabled={disabled}
              onChange={(event) =>
                set(
                  "reasoningEffort",
                  event.target.value as "low" | "medium" | "high"
                )
              }
            >
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
            </select>
            <input
              type="number"
              aria-label="Reasoning max tokens"
              data-testid="judge-reasoning-max-tokens"
              className={`w-28 ${inputClass}`}
              value={draft.reasoningMaxTokens}
              disabled={disabled}
              placeholder="max tokens"
              onChange={(event) =>
                set("reasoningMaxTokens", event.target.value)
              }
            />
          </div>
        )}
      </div>

      <label className="flex flex-col gap-1 text-sm">
        <span className="text-xs text-default-500">Custom prompt / rubric</span>
        <textarea
          aria-label="Custom prompt or rubric"
          data-testid="judge-prompt"
          rows={3}
          className={`${inputClass} font-mono text-xs`}
          value={draft.promptOverride}
          disabled={disabled}
          placeholder="Leave blank to use the default rubric."
          onChange={(event) => set("promptOverride", event.target.value)}
        />
      </label>

      {skills.length > 0 && (
        <div className="flex flex-col gap-1" data-testid="judge-skills">
          <span className="text-xs text-default-500">Skills</span>
          <div className="flex flex-col gap-1 rounded border border-default-200/60 px-2 py-1.5">
            {skills.map((skill) => {
              const checked = draft.selectedSkills.includes(skill.name);
              return (
                <label
                  key={skill.name}
                  className="flex items-center gap-1.5 text-sm"
                  title={skill.description || undefined}
                >
                  <input
                    type="checkbox"
                    data-testid={`judge-skill-${skill.name}`}
                    checked={checked}
                    disabled={disabled}
                    onChange={(event) =>
                      set(
                        "selectedSkills",
                        event.target.checked
                          ? [...draft.selectedSkills, skill.name]
                          : draft.selectedSkills.filter(
                              (name) => name !== skill.name
                            )
                      )
                    }
                  />
                  {skill.name}
                </label>
              );
            })}
          </div>
        </div>
      )}
    </fieldset>
  );
}
