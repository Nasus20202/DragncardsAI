"use client";

import {
  Input,
  Label,
  ListBox,
  ListBoxItem,
  Select,
  TextArea,
  TextField,
} from "@heroui/react";
import { SkillDefinitionResponse } from "@/features/shared/lib/types";
import {
  ComboSelect,
  dedupeItems,
} from "@/features/shared/components/combo-select";
import { ToggleInfoRow } from "@/features/shared/components/toggle-info-row";

/**
 * The labelled field wrappers every configuration panel in the dashboard is
 * built from: a small-caps field label, and the HeroUI text input, textarea,
 * select, searchable select, toggle row, and skills toggle list that sit under
 * one. They exist so the panels that configure the same things — the Play
 * settings panel and the History tab's judge configuration — render identical
 * controls instead of each hand-rolling its own.
 *
 * Presentational only: callers own the values, the change handlers, and which
 * fields to show.
 */

export interface FieldItem {
  value: string;
  label: string;
  /**
   * Renders the option greyed out and unpickable. Used to keep a choice
   * visible while explaining why it cannot be selected — a provider with no
   * models, for instance — rather than hiding it and leaving the user
   * wondering where it went.
   */
  disabled?: boolean;
}

/**
 * The red line a field shows when its current value cannot be accepted, and the
 * `aria-*` wiring that carries the same fact to assistive technology so the
 * problem is not conveyed by colour alone. Rendered only when there is one.
 */
function FieldError({ id, error }: { id: string; error?: string }) {
  if (!error) {
    return null;
  }
  return (
    <p className="text-xs text-danger" id={fieldErrorId(id)} role="alert">
      {error}
    </p>
  );
}

function fieldErrorId(id: string): string {
  return `${id}-error`;
}

/** The `aria-*` props a control carries while it has a problem to report. */
function fieldErrorProps(id: string, error?: string) {
  return error
    ? { "aria-invalid": true, "aria-describedby": fieldErrorId(id) }
    : {};
}

/** Small-caps caption above a field. */
export function FieldLabel({
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

export function TextInputField({
  id,
  label,
  ariaLabel,
  description,
  error,
  placeholder,
  value,
  disabled,
  inputTestId,
  onChange,
}: {
  id: string;
  label: string;
  /** Accessible name, when it needs to differ from the visible label. */
  ariaLabel?: string;
  /** One line under the label, for a field whose effect the label cannot state. */
  description?: string;
  /** Why the current value cannot be accepted. Shown under the control. */
  error?: string;
  placeholder?: string;
  value: string;
  disabled?: boolean;
  inputTestId?: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="grid gap-1">
      <FieldLabel id={id}>{label}</FieldLabel>
      {description && <p className="text-xs text-default-400">{description}</p>}
      <TextField
        fullWidth
        aria-label={ariaLabel ?? label}
        isDisabled={disabled}
      >
        <Input
          id={id}
          data-testid={inputTestId}
          placeholder={placeholder}
          value={value}
          {...fieldErrorProps(id, error)}
          onChange={(e) => onChange(e.target.value)}
        />
      </TextField>
      <FieldError id={id} error={error} />
    </div>
  );
}

export function TextareaField({
  id,
  label,
  ariaLabel,
  description,
  error,
  placeholder,
  rows,
  value,
  disabled,
  inputTestId,
  onChange,
}: {
  id: string;
  label: string;
  /** Accessible name, when it needs to differ from the visible label. */
  ariaLabel?: string;
  description?: string;
  /** Why the current value cannot be accepted. Shown under the control. */
  error?: string;
  placeholder?: string;
  rows: number;
  value: string;
  disabled?: boolean;
  inputTestId?: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="grid gap-1">
      <FieldLabel id={id}>{label}</FieldLabel>
      {description && <p className="text-xs text-default-400">{description}</p>}
      <TextField
        fullWidth
        aria-label={ariaLabel ?? label}
        isDisabled={disabled}
      >
        <TextArea
          id={id}
          data-testid={inputTestId}
          placeholder={placeholder}
          rows={rows}
          value={value}
          className="font-mono text-xs"
          {...fieldErrorProps(id, error)}
          onChange={(e) => onChange(e.target.value)}
        />
      </TextField>
      <FieldError id={id} error={error} />
    </div>
  );
}

export function SelectField({
  id,
  label,
  ariaLabel,
  items,
  value,
  disabled,
  triggerTestId,
  onChange,
}: {
  id: string;
  label: string;
  /** Accessible name, when it needs to differ from the visible label. */
  ariaLabel?: string;
  items: FieldItem[];
  value: string;
  disabled?: boolean;
  triggerTestId?: string;
  onChange: (v: string) => void;
}) {
  const name = ariaLabel ?? label;
  const renderItems = dedupeItems(items);
  return (
    <div className="grid gap-1">
      <FieldLabel id={id}>{label}</FieldLabel>
      <Select
        fullWidth
        aria-label={name}
        isDisabled={disabled}
        value={value}
        onChange={(nextValue) => {
          if (nextValue != null) {
            onChange(String(nextValue));
          }
        }}
      >
        <Select.Trigger aria-label={name} data-testid={triggerTestId}>
          <Select.Value />
          <Select.Indicator />
        </Select.Trigger>
        <Select.Popover>
          <ListBox aria-label={name}>
            {renderItems.map((item) => (
              <ListBoxItem
                key={item.value}
                id={item.value}
                isDisabled={item.disabled}
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

export function ComboSelectField({
  id,
  label,
  ariaLabel,
  items,
  value,
  disabled,
  inputTestId,
  onChange,
}: {
  id: string;
  label: string;
  /** Accessible name, when it needs to differ from the visible label. */
  ariaLabel?: string;
  items: FieldItem[];
  value: string;
  disabled?: boolean;
  inputTestId?: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="grid gap-1">
      <FieldLabel id={id}>{label}</FieldLabel>
      <ComboSelect
        label={ariaLabel ?? label}
        items={items}
        value={value}
        disabled={disabled}
        inputId={id}
        inputTestId={inputTestId}
        onChange={onChange}
      />
    </div>
  );
}

export function SwitchField({
  label,
  description,
  checked,
  disabled,
  onChange,
}: {
  id?: string;
  label: string;
  description?: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <ToggleInfoRow
      label={label}
      description={description}
      checked={checked}
      disabled={disabled}
      onChange={onChange}
    />
  );
}

/**
 * The bordered list of skill toggles shared by every panel that assigns skills.
 * A skill's description and metadata, when it has either, are reachable from the
 * row's info trigger. Renders nothing when no skills are offered.
 */
export function SkillToggleList({
  skills,
  selectedSkills,
  disabled,
  testId,
  skillTestId,
  onChange,
}: {
  skills: SkillDefinitionResponse[];
  selectedSkills: string[];
  disabled?: boolean;
  testId?: string;
  /** Per-row test id, derived from the skill name. */
  skillTestId?: (skillName: string) => string;
  onChange: (nextSelectedSkills: string[]) => void;
}) {
  if (skills.length === 0) {
    return null;
  }

  return (
    <div className="grid gap-2" data-testid={testId}>
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
              checked={selectedSkills.includes(skill.name)}
              disabled={disabled}
              testId={skillTestId?.(skill.name)}
              onChange={(checked) =>
                onChange(
                  checked
                    ? [...selectedSkills, skill.name]
                    : selectedSkills.filter((name) => name !== skill.name)
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
