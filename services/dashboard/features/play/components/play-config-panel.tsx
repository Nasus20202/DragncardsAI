"use client";

import {
  Button,
  ComboBox,
  Input,
  Label,
  ListBox,
  ListBoxItem,
  Select,
  Separator,
  TextArea,
  TextField,
} from "@heroui/react";
import { useEffect, useState } from "react";
import {
  McpAssignmentResponse,
  McpRegistryResponse,
  ProviderResponse,
  SessionDraft,
  SkillDefinitionResponse,
} from "@/features/shared/lib/types";
import { McpSection } from "@/features/play/components/mcp-section";
import { ToggleInfoRow } from "@/features/play/components/toggle-info-row";

/* ── Reusable field wrappers ─────────────────────────────────────── */

function FieldLabel({
  id,
  children,
}: {
  id: string;
  children: React.ReactNode;
}) {
  return (
    <Label
      className="block text-xs font-semibold uppercase tracking-wider text-default-400"
      htmlFor={id}
    >
      {children}
    </Label>
  );
}

function TextInputField({
  id,
  label,
  placeholder,
  value,
  onChange,
}: {
  id: string;
  label: string;
  placeholder?: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="grid gap-1">
      <FieldLabel id={id}>{label}</FieldLabel>
      <TextField fullWidth aria-label={label}>
        <Input
          id={id}
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      </TextField>
    </div>
  );
}

function TextareaField({
  id,
  label,
  description,
  rows,
  value,
  onChange,
}: {
  id: string;
  label: string;
  description?: string;
  rows: number;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="grid gap-1">
      <FieldLabel id={id}>{label}</FieldLabel>
      {description && <p className="text-xs text-default-400">{description}</p>}
      <TextField fullWidth aria-label={label}>
        <TextArea
          id={id}
          rows={rows}
          value={value}
          className="font-mono text-xs"
          onChange={(e) => onChange(e.target.value)}
        />
      </TextField>
    </div>
  );
}

function SelectField({
  id,
  label,
  items,
  value,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  items: { value: string; label: string }[];
  value: string;
  disabled?: boolean;
  onChange: (v: string) => void;
}) {
  return (
    <div className="grid gap-1">
      <FieldLabel id={id}>{label}</FieldLabel>
      <Select
        fullWidth
        aria-label={label}
        isDisabled={disabled}
        value={value}
        onChange={(nextValue) => {
          if (nextValue != null) {
            onChange(String(nextValue));
          }
        }}
      >
        <Select.Trigger aria-label={label}>
          <Select.Value />
          <Select.Indicator />
        </Select.Trigger>
        <Select.Popover>
          <ListBox aria-label={label}>
            {items.map((item) => (
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
  );
}

function ComboSelectField({
  id,
  label,
  items,
  value,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  items: { value: string; label: string }[];
  value: string;
  disabled?: boolean;
  onChange: (v: string) => void;
}) {
  const [inputValue, setInputValue] = useState(
    () => items.find((i) => i.value === value)?.label ?? value
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setInputValue(items.find((i) => i.value === value)?.label ?? value);
  }, [value, items]);

  const filtered = inputValue
    ? items.filter((i) =>
        i.label.toLowerCase().includes(inputValue.toLowerCase())
      )
    : items;

  return (
    <div className="grid gap-1">
      <FieldLabel id={id}>{label}</FieldLabel>
      <ComboBox
        fullWidth
        aria-label={label}
        isDisabled={disabled}
        value={value}
        inputValue={inputValue}
        onInputChange={setInputValue}
        onOpenChange={(isOpen) => {
          if (isOpen) {
            // Clear the input so the full list is shown
            setInputValue("");
          } else {
            // Restore the label of the committed value if nothing was selected
            setInputValue(items.find((i) => i.value === value)?.label ?? value);
          }
        }}
        onChange={(nextValue) => {
          if (nextValue) {
            const item = items.find((i) => i.value === String(nextValue));
            setInputValue(item?.label ?? String(nextValue));
            onChange(String(nextValue));
          }
        }}
      >
        <ComboBox.InputGroup>
          <Input id={id} />
          <ComboBox.Trigger />
        </ComboBox.InputGroup>
        <ComboBox.Popover>
          <ListBox aria-label={label}>
            {filtered.map((item) => (
              <ListBoxItem
                key={item.value}
                id={item.value}
                textValue={item.label}
              >
                {item.label}
              </ListBoxItem>
            ))}
          </ListBox>
        </ComboBox.Popover>
      </ComboBox>
    </div>
  );
}

function SwitchField({
  label,
  description,
  checked,
  onChange,
}: {
  id?: string;
  label: string;
  description?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <ToggleInfoRow
      label={label}
      description={description}
      checked={checked}
      onChange={onChange}
    />
  );
}

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

function SkillsSection({
  draft,
  skills,
  set,
}: {
  draft: SessionDraft;
  skills: SkillDefinitionResponse[];
  set: <K extends keyof SessionDraft>(key: K, value: SessionDraft[K]) => void;
}) {
  if (skills.length === 0) {
    return null;
  }

  return (
    <div className="grid gap-2">
      <p className="text-xs font-semibold uppercase tracking-wider text-default-400">
        Skills
      </p>
      <div className="grid gap-1 rounded-lg border border-default-200/60 px-3 py-2">
        {skills.map((skill) => {
          const metaStr = Object.entries(skill.metadata ?? {})
            .map(([key, value]) => `${key}: ${value}`)
            .join(" · ");
          const hasInfo = Boolean(skill.description || metaStr);
          return (
            <ToggleInfoRow
              key={skill.name}
              label={skill.name}
              checked={draft.selectedSkills.includes(skill.name)}
              onChange={(checked) =>
                set(
                  "selectedSkills",
                  checked
                    ? [...draft.selectedSkills, skill.name]
                    : draft.selectedSkills.filter((name) => name !== skill.name)
                )
              }
              infoLabel={hasInfo ? `Info about ${skill.name}` : undefined}
              infoContent={
                hasInfo ? (
                  <div className="space-y-1 p-1">
                    {skill.description && (
                      <p className="text-xs">{skill.description}</p>
                    )}
                    {metaStr && (
                      <p className="text-[11px] opacity-70">{metaStr}</p>
                    )}
                  </div>
                ) : undefined
              }
            />
          );
        })}
      </div>
    </div>
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

  const providerItems = providers.map((p) => ({
    value: p.provider_id,
    label: p.provider_id,
  }));
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

            <SkillsSection draft={draft} skills={skills} set={set} />

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
