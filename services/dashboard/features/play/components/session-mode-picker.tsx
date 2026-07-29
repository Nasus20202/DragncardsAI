"use client";

import { SelectField } from "@/features/shared/components/form-fields";
import { SessionMode } from "@/features/shared/lib/types";

const MODE_ITEMS: { value: SessionMode; label: string; description: string }[] =
  [
    {
      value: "chat",
      label: "Chat (single agent)",
      description: "One agent plays and talks to you. The default.",
    },
    {
      value: "orchestrated",
      label: "Orchestrated (agent per player)",
      description:
        "An orchestrator runs the game flow and prompts one persistent agent per player seat.",
    },
  ];

/**
 * Chooses how a session is driven: today's single-agent chat, or an
 * orchestrated game with one persistent agent per player seat.
 *
 * The orchestrator fixes the mode once a session has run a prompt, so the
 * picker is disabled with the reason spelled out rather than hidden — the
 * choice stays visible on a started session instead of disappearing.
 */
export function SessionModePicker({
  value,
  onChange,
  disabled,
  disabledReason,
}: {
  value: SessionMode;
  onChange: (next: SessionMode) => void;
  disabled?: boolean;
  disabledReason?: string;
}) {
  const selected = MODE_ITEMS.find((item) => item.value === value);

  return (
    <div className="grid gap-1">
      <SelectField
        id="cfg-session-mode"
        label="Session mode"
        items={MODE_ITEMS.map(({ value: itemValue, label }) => ({
          value: itemValue,
          label,
        }))}
        value={value}
        disabled={disabled}
        triggerTestId="session-mode-trigger"
        onChange={(next) =>
          onChange(next === "orchestrated" ? "orchestrated" : "chat")
        }
      />
      {selected && (
        <p className="text-xs text-default-400">{selected.description}</p>
      )}
      {disabled && disabledReason && (
        <p className="text-xs text-default-500">{disabledReason}</p>
      )}
    </div>
  );
}
