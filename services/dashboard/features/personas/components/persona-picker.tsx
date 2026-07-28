"use client";

import { useEffect, useState } from "react";

import { listPersonas } from "@/features/play/lib/client-api";
import { SelectField } from "@/features/shared/components/form-fields";
import { PersonaResponse } from "@/features/shared/lib/types";

/** The option meaning "no persona": subagents copy the session's configuration. */
export const NO_PERSONA_VALUE = "";
const NO_PERSONA_LABEL = "No persona (subagents copy this session)";

/**
 * Chooses which persona this session's subagents are started from by default.
 *
 * Loads the persona catalogue itself, because a picker for a deployment-global
 * list has no reason to be threaded through the play-session state: the list
 * belongs to no session. When no personas are defined the picker renders
 * nothing, so a feature nobody has configured adds no empty control to the
 * panel.
 */
export function PersonaPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (next: string) => void;
}) {
  const [personas, setPersonas] = useState<PersonaResponse[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    // A failed load is not fatal: the picker simply stays hidden, exactly as it
    // does for a deployment with no personas.
    listPersonas()
      .then((loaded) => {
        if (!cancelled) {
          setPersonas(loaded);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPersonas([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // A session already pinned to a persona keeps it listed even if the catalogue
  // has not arrived, so selecting a session never silently clears its choice.
  const known = personas ?? [];
  if (known.length === 0 && !value) {
    return null;
  }

  const items = [
    { value: NO_PERSONA_VALUE, label: NO_PERSONA_LABEL },
    ...known.map((persona) => ({
      value: persona.name,
      label: persona.display_name
        ? `${persona.name} — ${persona.display_name}`
        : persona.name,
    })),
  ];
  if (value && !known.some((persona) => persona.name === value)) {
    items.push({ value, label: value });
  }

  return (
    <SelectField
      id="cfg-subagent-persona"
      label="Subagent persona"
      items={items}
      value={value}
      triggerTestId="subagent-persona-trigger"
      onChange={onChange}
    />
  );
}
