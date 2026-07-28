"use client";

import { Button, Separator } from "@heroui/react";
import {
  McpAssignmentResponse,
  McpRegistryResponse,
  ProviderResponse,
  SessionDraft,
  SkillDefinitionResponse,
} from "@/features/shared/lib/types";
import {
  ComboSelectField,
  SelectField,
  SkillToggleList,
  SwitchField,
  TextInputField,
  TextareaField,
} from "@/features/shared/components/form-fields";
import { isWorking } from "@/features/play/lib/session-draft";
import { McpSection } from "@/features/play/components/mcp-section";

function ReasoningSection({
  draft,
  set,
}: {
  draft: SessionDraft;
  set: <K extends keyof SessionDraft>(key: K, value: SessionDraft[K]) => void;
}) {
  return (
    <>
      <SwitchField
        id="cfg-reasoning"
        label="Reasoning stream"
        description="Stream the model's chain-of-thought."
        checked={draft.reasoning.enabled}
        onChange={(value) =>
          set("reasoning", { ...draft.reasoning, enabled: value })
        }
      />

      {draft.reasoning.enabled && (
        <>
          <SelectField
            id="cfg-effort"
            label="Reasoning effort"
            items={[
              { value: "low", label: "Low" },
              { value: "medium", label: "Medium" },
              { value: "high", label: "High" },
            ]}
            value={draft.reasoning.effort}
            onChange={(value) =>
              set("reasoning", {
                ...draft.reasoning,
                effort: value as "low" | "medium" | "high",
              })
            }
          />
          <TextInputField
            id="cfg-rtokens"
            label="Reasoning max tokens"
            placeholder="e.g. 4096"
            value={draft.reasoning.maxTokens}
            onChange={(value) =>
              set("reasoning", { ...draft.reasoning, maxTokens: value })
            }
          />
        </>
      )}
    </>
  );
}

function AdvancedJsonSection({
  draft,
  set,
}: {
  draft: SessionDraft;
  set: <K extends keyof SessionDraft>(key: K, value: SessionDraft[K]) => void;
}) {
  return (
    <>
      <p className="text-xs font-semibold uppercase tracking-wider text-default-400">
        Advanced JSON
      </p>

      <TextareaField
        id="cfg-gateway"
        label="Gateway options"
        rows={3}
        value={draft.gatewayOptionsText}
        onChange={(value) => set("gatewayOptionsText", value)}
      />
      <TextareaField
        id="cfg-popts"
        label="Provider options"
        rows={3}
        value={draft.providerOptionsText}
        onChange={(value) => set("providerOptionsText", value)}
      />
    </>
  );
}

/* ── Main component ──────────────────────────────────────────────── */

interface Props {
  draft: SessionDraft;
  providers: ProviderResponse[];
  modelOptions: string[];
  skills: SkillDefinitionResponse[];
  mcps: McpAssignmentResponse[];
  isBusy: boolean;
  canSave: boolean;
  isOpen: boolean;
  onDraftChange: (next: SessionDraft) => void;
  onClose: () => void;
  onSave: () => void;
  onTerminate: () => void;
  onToggleMcp: (mcpName: string, enabled: boolean) => Promise<void>;
  onAddMcp: (mcp: McpRegistryResponse) => Promise<void>;
  onDeleteMcp: (mcpName: string) => Promise<void>;
}

export function PlayConfigPanel({
  draft,
  providers,
  modelOptions,
  skills,
  mcps,
  isBusy,
  canSave,
  isOpen,
  onDraftChange,
  onClose,
  onSave,
  onTerminate,
  onToggleMcp,
  onAddMcp,
  onDeleteMcp,
}: Props) {
  if (!isOpen) return null;

  // A provider with no models — the state a missing API key produces — cannot be
  // configured: its model list is empty, so picking it would strand the user on a
  // disabled model picker holding another provider's model. Such providers stay
  // listed and labelled (so the reason is visible, and a session already pinned
  // to one still shows its provider) but cannot be selected.
  const providerItems = providers.map((p) => {
    const usable = isWorking(p);
    return {
      value: p.provider_id,
      label: usable ? p.provider_id : `${p.provider_id} (no models)`,
      disabled: !usable,
    };
  });
  const modelItems = modelOptions.length
    ? modelOptions.map((m) => ({ value: m, label: m }))
    : [{ value: draft.modelName, label: draft.modelName }];

  function set<K extends keyof SessionDraft>(key: K, value: SessionDraft[K]) {
    onDraftChange({ ...draft, [key]: value });
  }

  return (
    <>
      <button
        type="button"
        aria-label="Close settings overlay"
        className="fixed inset-0 z-20 bg-black/40 md:hidden"
        onClick={onClose}
      />
      <aside className="fixed inset-y-0 right-0 z-30 flex w-full max-w-sm flex-col border-l border-default-200/60 bg-background shadow-2xl md:static md:z-auto md:w-96 md:max-w-none md:shrink-0 md:shadow-none">
        {/* Header */}
        <div className="flex h-10 shrink-0 items-center justify-between border-b border-default-200/60 px-4">
          <span className="text-xs font-semibold uppercase tracking-wider text-default-400">
            Settings
          </span>
          <Button
            aria-label="Close settings"
            isIconOnly
            size="sm"
            variant="ghost"
            onPress={onClose}
          >
            <span aria-hidden="true">✕</span>
          </Button>
        </div>

        {/* Scrollable body */}
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          <div className="grid gap-4">
            <TextInputField
              id="cfg-name"
              label="Session name"
              placeholder="e.g. Solo Marvel Champions"
              value={draft.name}
              onChange={(v) => set("name", v)}
            />

            <Separator />

            <SelectField
              id="cfg-provider"
              label="Provider"
              items={providerItems}
              value={draft.providerId}
              onChange={(v) => set("providerId", v)}
            />

            <ComboSelectField
              id="cfg-model"
              label="Model"
              items={modelItems}
              value={draft.modelName}
              disabled={modelOptions.length === 0}
              onChange={(v) => set("modelName", v)}
            />

            <Separator />

            <ReasoningSection draft={draft} set={set} />

            <Separator />

            <SkillToggleList
              skills={skills}
              selectedSkills={draft.selectedSkills}
              onChange={(next) => set("selectedSkills", next)}
            />

            <Separator />

            <McpSection
              mcps={mcps}
              isBusy={isBusy}
              onToggle={onToggleMcp}
              onAdd={onAddMcp}
              onDelete={onDeleteMcp}
            />

            <Separator />

            <TextInputField
              id="cfg-rmsg-limit"
              label="Recent message limit"
              placeholder="Unlimited"
              value={draft.recentMessageLimit}
              onChange={(v) => set("recentMessageLimit", v)}
            />

            <TextInputField
              id="cfg-rtool-limit"
              label="Recent tool exchange limit"
              placeholder="Unlimited"
              value={draft.recentToolExchangeLimit}
              onChange={(v) => set("recentToolExchangeLimit", v)}
            />

            <Separator />

            <AdvancedJsonSection draft={draft} set={set} />
          </div>
        </div>

        {/* Footer */}
        <div className="flex shrink-0 justify-end gap-2 border-t border-default-200/60 px-4 py-3">
          <Button
            aria-label="Terminate session"
            isDisabled={!canSave || isBusy}
            variant="ghost"
            onPress={onTerminate}
          >
            Terminate
          </Button>
          <Button
            aria-label="Save configuration"
            isDisabled={!canSave || isBusy}
            variant="primary"
            onPress={onSave}
          >
            Save
          </Button>
        </div>
      </aside>
    </>
  );
}
