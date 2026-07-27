"use client";

import {
  Checkbox,
  Input,
  ListBox,
  ListBoxItem,
  Select,
  TextArea,
  TextField,
} from "@heroui/react";

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

const REASONING_EFFORTS = ["low", "medium", "high"] as const;

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

  // The provider list falls back to the current draft value so the select is
  // never empty, and mirrors the "(unavailable)" suffix from the source data.
  const providerItems =
    providers.length === 0
      ? [{ value: draft.providerId, label: draft.providerId }]
      : providers.map((provider) => ({
          value: provider.provider_id,
          label: `${provider.provider_id}${
            provider.available === false ? " (unavailable)" : ""
          }`,
        }));

  // Same fallback for the model list: keep the current model selectable even
  // when it is not among the provider's offerings.
  const modelItems = modelOptions.includes(draft.modelName)
    ? modelOptions.map((model) => ({ value: model, label: model }))
    : [
        { value: draft.modelName, label: draft.modelName },
        ...modelOptions.map((model) => ({ value: model, label: model })),
      ];

  return (
    <fieldset
      className="flex flex-col gap-3 rounded-lg border border-default-200/60 p-3"
      data-testid="judge-config"
      aria-label="Judge configuration"
    >
      <span className="text-xs font-semibold uppercase tracking-wide text-default-400">
        Judge
      </span>

      <div className="flex flex-col gap-1 text-sm">
        <span className="text-xs text-default-500">Provider</span>
        <Select
          aria-label="Judge provider"
          value={draft.providerId}
          isDisabled={disabled}
          onChange={(next) => {
            if (next == null) return;
            const providerId = String(next);
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
          <Select.Trigger
            aria-label="Judge provider"
            data-testid="judge-provider"
          >
            <Select.Value />
            <Select.Indicator />
          </Select.Trigger>
          <Select.Popover>
            <ListBox aria-label="Judge provider">
              {providerItems.map((item) => (
                <ListBoxItem
                  key={item.value}
                  id={item.value}
                  textValue={item.label}
                >
                  {item.label}
                </ListBoxItem>
              ))}
            </ListBox>
          </Select.Popover>
        </Select>
      </div>

      <div className="flex flex-col gap-1 text-sm">
        <span className="text-xs text-default-500">Model</span>
        <Select
          aria-label="Judge model"
          value={draft.modelName}
          isDisabled={disabled || modelOptions.length === 0}
          onChange={(next) => {
            if (next != null) set("modelName", String(next));
          }}
        >
          <Select.Trigger aria-label="Judge model" data-testid="judge-model">
            <Select.Value />
            <Select.Indicator />
          </Select.Trigger>
          <Select.Popover>
            <ListBox aria-label="Judge model">
              {modelItems.map((item) => (
                <ListBoxItem
                  key={item.value}
                  id={item.value}
                  textValue={item.label}
                >
                  {item.label}
                </ListBoxItem>
              ))}
            </ListBox>
          </Select.Popover>
        </Select>
      </div>

      <div className="flex flex-col gap-2">
        <Checkbox
          data-testid="judge-reasoning-enabled"
          isSelected={draft.reasoningEnabled}
          isDisabled={disabled}
          onChange={(next) => set("reasoningEnabled", next)}
        >
          <Checkbox.Content className="flex items-center gap-1.5 text-sm">
            <Checkbox.Control>
              <Checkbox.Indicator />
            </Checkbox.Control>
            <span>Reasoning</span>
          </Checkbox.Content>
        </Checkbox>
        {draft.reasoningEnabled && (
          <div className="flex flex-wrap items-center gap-2 pl-5">
            <Select
              aria-label="Reasoning effort"
              value={draft.reasoningEffort}
              isDisabled={disabled}
              onChange={(next) => {
                if (next != null) {
                  set(
                    "reasoningEffort",
                    String(next) as "low" | "medium" | "high"
                  );
                }
              }}
            >
              <Select.Trigger
                aria-label="Reasoning effort"
                data-testid="judge-reasoning-effort"
              >
                <Select.Value />
                <Select.Indicator />
              </Select.Trigger>
              <Select.Popover>
                <ListBox aria-label="Reasoning effort">
                  {REASONING_EFFORTS.map((effort) => (
                    <ListBoxItem key={effort} id={effort} textValue={effort}>
                      {effort}
                    </ListBoxItem>
                  ))}
                </ListBox>
              </Select.Popover>
            </Select>
            <TextField aria-label="Reasoning max tokens" isDisabled={disabled}>
              <Input
                type="number"
                aria-label="Reasoning max tokens"
                data-testid="judge-reasoning-max-tokens"
                className="w-28"
                value={draft.reasoningMaxTokens}
                placeholder="max tokens"
                onChange={(event) =>
                  set("reasoningMaxTokens", event.target.value)
                }
              />
            </TextField>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-1 text-sm">
        <span className="text-xs text-default-500">Custom prompt / rubric</span>
        <TextField aria-label="Custom prompt or rubric" isDisabled={disabled}>
          <TextArea
            aria-label="Custom prompt or rubric"
            data-testid="judge-prompt"
            rows={3}
            className="font-mono text-xs"
            value={draft.promptOverride}
            placeholder="Leave blank to use the default rubric."
            onChange={(event) => set("promptOverride", event.target.value)}
          />
        </TextField>
      </div>

      {skills.length > 0 && (
        <div className="flex flex-col gap-1" data-testid="judge-skills">
          <span className="text-xs text-default-500">Skills</span>
          <div className="flex flex-col gap-1 rounded border border-default-200/60 px-2 py-1.5">
            {skills.map((skill) => {
              const checked = draft.selectedSkills.includes(skill.name);
              return (
                <Checkbox
                  key={skill.name}
                  data-testid={`judge-skill-${skill.name}`}
                  isSelected={checked}
                  isDisabled={disabled}
                  onChange={(next) =>
                    set(
                      "selectedSkills",
                      next
                        ? [...draft.selectedSkills, skill.name]
                        : draft.selectedSkills.filter(
                            (name) => name !== skill.name
                          )
                    )
                  }
                >
                  <Checkbox.Content className="flex items-center gap-1.5 text-sm">
                    <Checkbox.Control>
                      <Checkbox.Indicator />
                    </Checkbox.Control>
                    {/* Hero UI's Checkbox props do not accept `title`; the
                        description tooltip lives on the skill name. */}
                    <span title={skill.description || undefined}>
                      {skill.name}
                    </span>
                  </Checkbox.Content>
                </Checkbox>
              );
            })}
          </div>
        </div>
      )}
    </fieldset>
  );
}
