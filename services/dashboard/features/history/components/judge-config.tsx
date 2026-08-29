"use client";

import {
  ProviderResponse,
  SkillDefinitionResponse,
} from "@/features/shared/lib/types";
import {
  JudgeDraft,
  modelOptionsForProvider,
  pruneSkillReferences,
} from "@/features/history/lib/judge-config";
import { reasoningEffortsForModel } from "@/features/play/lib/session-draft";
import { JudgeSkillReferences } from "@/features/history/components/judge-skill-references";
import {
  ComboSelectField,
  SelectField,
  SkillToggleList,
  TextInputField,
  TextareaField,
} from "@/features/shared/components/form-fields";
import { ToggleInfoRow } from "@/features/shared/components/toggle-info-row";

export interface JudgeConfigPanelProps {
  draft: JudgeDraft;
  providers: ProviderResponse[];
  skills: SkillDefinitionResponse[];
  disabled?: boolean;
  onChange: (next: JudgeDraft) => void;
}

/**
 * Play-parity judge configuration controls for the Evaluate panel: provider +
 * model selects (sourced from listProviders), reasoning toggle/effort/max
 * tokens, a custom prompt/rubric textarea, a skills multiselect (from
 * listAvailableSkills), and the reference files of the selected skills. All
 * values feed {@link assembleJudgeConfig}.
 *
 * Every control is one of the shared field components the Play settings panel is
 * built from, so the same setting looks and behaves the same in both tabs.
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
  const selectedProvider = providers.find(
    (provider) => provider.provider_id === draft.providerId
  );
  const reasoningEfforts = reasoningEffortsForModel(
    selectedProvider,
    draft.modelName
  );
  const reasoningEnabled =
    draft.reasoningEnabled && reasoningEfforts.length > 0;

  // Keep the drafted model selectable even when the provider does not offer it,
  // mirroring the fallback `<option>` the plain select used to render.
  const modelItems = (
    modelOptions.includes(draft.modelName)
      ? modelOptions
      : [draft.modelName, ...modelOptions]
  ).map((model) => ({ value: model, label: model }));

  // With no catalogue at all the drafted provider is still the current one, so
  // offer it rather than an empty list.
  const providerItems =
    providers.length === 0
      ? [{ value: draft.providerId, label: draft.providerId }]
      : providers.map((provider) => ({
          value: provider.provider_id,
          label:
            provider.available === false
              ? `${provider.provider_id} (unavailable)`
              : provider.provider_id,
        }));

  return (
    <fieldset
      className="flex flex-col gap-3 rounded-lg border border-default-200/60 p-3"
      data-testid="judge-config"
      aria-label="Judge configuration"
    >
      <span className="text-xs font-semibold uppercase tracking-wide text-default-400">
        Judge
      </span>

      <SelectField
        id="judge-provider-field"
        label="Provider"
        ariaLabel="Judge provider"
        items={providerItems}
        value={draft.providerId}
        disabled={disabled}
        triggerTestId="judge-provider"
        onChange={(providerId) => {
          const nextModels = modelOptionsForProvider(
            providers,
            providerId,
            draft.modelName
          );
          // Clamp the model to the newly-selected provider's offerings.
          const modelName = nextModels.includes(draft.modelName)
            ? draft.modelName
            : (nextModels[0] ?? draft.modelName);
          const nextProvider = providers.find(
            (provider) => provider.provider_id === providerId
          );
          const nextEfforts = reasoningEffortsForModel(nextProvider, modelName);
          onChange({
            ...draft,
            providerId,
            modelName,
            reasoningEnabled: draft.reasoningEnabled && nextEfforts.length > 0,
            reasoningEffort: nextEfforts.includes(draft.reasoningEffort)
              ? draft.reasoningEffort
              : (nextEfforts[0] ?? ""),
          });
        }}
      />

      <ComboSelectField
        id="judge-model-field"
        label="Model"
        ariaLabel="Judge model"
        items={modelItems}
        value={draft.modelName}
        disabled={disabled || modelOptions.length === 0}
        inputTestId="judge-model"
        onChange={(model) => {
          const nextEfforts = reasoningEffortsForModel(selectedProvider, model);
          onChange({
            ...draft,
            modelName: model,
            reasoningEnabled: draft.reasoningEnabled && nextEfforts.length > 0,
            reasoningEffort: nextEfforts.includes(draft.reasoningEffort)
              ? draft.reasoningEffort
              : (nextEfforts[0] ?? ""),
          });
        }}
      />

      <ToggleInfoRow
        label="Reasoning"
        checked={reasoningEnabled}
        disabled={disabled || reasoningEfforts.length === 0}
        testId="judge-reasoning-enabled"
        onChange={(enabled) => set("reasoningEnabled", enabled)}
      />

      {reasoningEnabled && (
        <>
          <SelectField
            id="judge-effort-field"
            label="Reasoning effort"
            items={reasoningEfforts.map((effort) => ({
              value: effort,
              label: effort.charAt(0).toUpperCase() + effort.slice(1),
            }))}
            value={draft.reasoningEffort}
            disabled={disabled}
            triggerTestId="judge-reasoning-effort"
            onChange={(effort) => set("reasoningEffort", effort)}
          />
          <TextInputField
            id="judge-max-tokens-field"
            label="Reasoning max tokens"
            placeholder="e.g. 4096"
            value={draft.reasoningMaxTokens}
            disabled={disabled}
            inputTestId="judge-reasoning-max-tokens"
            onChange={(maxTokens) => set("reasoningMaxTokens", maxTokens)}
          />
        </>
      )}

      <TextareaField
        id="judge-prompt-field"
        label="Custom prompt / rubric"
        ariaLabel="Custom prompt or rubric"
        rows={3}
        placeholder="Leave blank to use the default rubric."
        value={draft.promptOverride}
        disabled={disabled}
        inputTestId="judge-prompt"
        onChange={(prompt) => set("promptOverride", prompt)}
      />

      <SkillToggleList
        skills={skills}
        selectedSkills={draft.selectedSkills}
        disabled={disabled}
        testId="judge-skills"
        skillTestId={(name) => `judge-skill-${name}`}
        onChange={(selectedSkills) =>
          // Deselecting a skill takes its reference files with it, in the same
          // update, so the draft never carries an orphaned reference.
          onChange({
            ...draft,
            selectedSkills,
            selectedSkillReferences: pruneSkillReferences(
              selectedSkills,
              draft.selectedSkillReferences
            ),
          })
        }
      />

      <JudgeSkillReferences
        skills={skills}
        selectedSkills={draft.selectedSkills}
        selectedSkillReferences={draft.selectedSkillReferences}
        disabled={disabled}
        onChange={(next) => set("selectedSkillReferences", next)}
      />
    </fieldset>
  );
}
