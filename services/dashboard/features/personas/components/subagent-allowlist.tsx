"use client";

import { useEffect, useState } from "react";

import { listPersonas } from "@/features/play/lib/client-api";
import { ToggleInfoRow } from "@/features/shared/components/toggle-info-row";
import { PersonaResponse } from "@/features/shared/lib/types";

/**
 * Which personas this session's agent may start a subagent from.
 *
 * Built like the skill toggle list above it — a row per catalogue entry with a
 * switch — because it is the same kind of control: a per-session selection from
 * a deployment-global catalogue.
 *
 * The one thing this component must never do is leave the empty state to be
 * inferred. Nothing ticked means **no** persona may be spawned, and the panel
 * says so in words rather than showing an unticked list that could equally read
 * as "unrestricted". A security-shaped control that silently means "everything"
 * is worse than no control, so the summary line under the heading always states
 * which of the two states this session is in.
 *
 * Loads the catalogue itself, for the same reason `PersonaPicker` does: the list
 * belongs to no session and has no business in the play-session state.
 */
export function SubagentAllowlist({
  selected,
  onChange,
}: {
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  const [personas, setPersonas] = useState<PersonaResponse[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    // A failed load leaves the section hidden rather than showing an empty list
    // that would read as "no personas exist" — the same fallback the picker uses.
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

  const known = personas ?? [];
  if (known.length === 0) {
    return null;
  }

  const allowedCount = known.filter((persona) =>
    selected.includes(persona.name)
  ).length;

  return (
    <div className="grid gap-2" data-testid="subagent-allowlist">
      <p className="text-xs font-semibold uppercase tracking-wider text-default-400">
        Allowed subagents
      </p>
      <p
        className={
          allowedCount === 0
            ? "text-xs text-warning"
            : "text-xs text-default-500"
        }
        data-testid="subagent-allowlist-summary"
      >
        {allowedCount === 0
          ? "No personas allowed. This session can only spawn subagents that copy its own configuration; naming any persona is refused by the server."
          : `${allowedCount} of ${known.length} personas allowed. Naming any other persona is refused by the server.`}
      </p>
      <div className="grid gap-1 rounded-lg border border-default-200/60 px-3 py-2">
        {known.map((persona) => {
          const label = persona.display_name
            ? `${persona.name} — ${persona.display_name}`
            : persona.name;
          const description = (persona.description ?? "").trim();
          return (
            <ToggleInfoRow
              key={persona.name}
              label={label}
              checked={selected.includes(persona.name)}
              testId={`subagent-allow-${persona.name}`}
              onChange={(checked) =>
                onChange(
                  checked
                    ? [...selected, persona.name]
                    : selected.filter((name) => name !== persona.name)
                )
              }
              infoLabel={description ? `About ${persona.name}` : undefined}
              infoContent={
                description ? (
                  <div className="space-y-1 p-1">
                    <p className="text-xs">{description}</p>
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
