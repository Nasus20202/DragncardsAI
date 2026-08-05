"use client";

import { Button } from "@heroui/react";

import { SkillDefinitionResponse } from "@/features/shared/lib/types";
import { ToggleInfoRow } from "@/features/shared/components/toggle-info-row";

export interface JudgeSkillReferencesProps {
  skills: SkillDefinitionResponse[];
  selectedSkills: string[];
  selectedSkillReferences: string[];
  disabled?: boolean;
  onChange: (nextSelectedSkillReferences: string[]) => void;
}

/** Compact enough to sit on a settings row without stretching it. */
const BUTTON_CLASS = "h-6 min-h-6 px-2";

/**
 * Append `candidates` that are not selected yet, in catalogue order, leaving the
 * existing selection's order and contents untouched. Selecting over a partial
 * selection therefore neither reorders nor duplicates what is already there.
 */
function withAdded(selected: string[], candidates: string[]): string[] {
  const present = new Set(selected);
  return [...selected, ...candidates.filter((entry) => !present.has(entry))];
}

/** Drop every one of `candidates` from the selection, keeping the rest as-is. */
function withRemoved(selected: string[], candidates: string[]): string[] {
  const removing = new Set(candidates);
  return selected.filter((entry) => !removing.has(entry));
}

/**
 * Reference-file toggles for the skills the judge has been given, grouped per
 * skill. A skill only appears once it is selected AND it ships reference files,
 * so the section stays empty (renders nothing) until there is something to pick.
 *
 * Each toggle's value is the full `"<skill-name>/<relative-path>.md"` selection
 * string the eval-service expects in `judge.skill_references`.
 *
 * There is no count limit: the eval-service bounds the selection by *size*,
 * against a budget derived from the judge model's context window, and refuses an
 * over-budget request with a 400 that names the measured total, the budget, and
 * the settings that would raise it. A count cap here would only stop selections
 * that fit. Hence select-all, per-skill All/None, and a `selected/total` counter
 * rather than a `selected/8` one.
 *
 * Deliberately a separate component from the shared `SkillToggleList`: that one
 * is also the Play settings panel's skills control and must not grow a second
 * shape.
 */
export function JudgeSkillReferences({
  skills,
  selectedSkills,
  selectedSkillReferences,
  disabled,
  onChange,
}: JudgeSkillReferencesProps) {
  const groups = skills
    .filter(
      (skill) =>
        selectedSkills.includes(skill.name) &&
        (skill.references?.length ?? 0) > 0
    )
    .map((skill) => ({
      name: skill.name,
      selections: (skill.references ?? []).map((reference) => ({
        reference,
        selection: `${skill.name}/${reference}`,
      })),
    }));

  if (groups.length === 0) {
    return null;
  }

  const selected = new Set(selectedSkillReferences);
  const everySelection = groups.flatMap((group) =>
    group.selections.map((entry) => entry.selection)
  );
  const selectedHere = everySelection.filter((entry) => selected.has(entry));

  return (
    <div className="grid gap-2" data-testid="judge-skill-references">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-default-400">
          Skill references
          <span className="ml-2 normal-case tracking-normal text-default-300">
            {/* `selectedHere`, not the whole draft: a selection for a skill the
                catalogue no longer offers would otherwise render as "5/4". */}
            {selectedHere.length}/{everySelection.length}
          </span>
        </p>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className={BUTTON_CLASS}
            data-testid="judge-skill-references-select-all"
            isDisabled={
              disabled || selectedHere.length === everySelection.length
            }
            onPress={() =>
              onChange(withAdded(selectedSkillReferences, everySelection))
            }
          >
            Select all
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className={BUTTON_CLASS}
            data-testid="judge-skill-references-clear-all"
            isDisabled={disabled || selectedHere.length === 0}
            onPress={() =>
              onChange(withRemoved(selectedSkillReferences, everySelection))
            }
          >
            Clear all
          </Button>
        </div>
      </div>
      <div className="grid gap-2 rounded-lg border border-default-200/60 px-3 py-2">
        {groups.map((group) => {
          const groupSelections = group.selections.map(
            (entry) => entry.selection
          );
          const groupSelectedCount = groupSelections.filter((entry) =>
            selected.has(entry)
          ).length;
          return (
            <div key={group.name} className="grid gap-1">
              <div className="flex items-center justify-between gap-2">
                <p className="text-[11px] font-medium text-default-400">
                  {group.name}
                </p>
                <div className="flex items-center gap-1">
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className={BUTTON_CLASS}
                    aria-label={`Select all ${group.name} references`}
                    data-testid={`judge-skill-references-group-all-${group.name}`}
                    isDisabled={
                      disabled || groupSelectedCount === groupSelections.length
                    }
                    onPress={() =>
                      onChange(
                        withAdded(selectedSkillReferences, groupSelections)
                      )
                    }
                  >
                    All
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className={BUTTON_CLASS}
                    aria-label={`Clear ${group.name} references`}
                    data-testid={`judge-skill-references-group-none-${group.name}`}
                    isDisabled={disabled || groupSelectedCount === 0}
                    onPress={() =>
                      onChange(
                        withRemoved(selectedSkillReferences, groupSelections)
                      )
                    }
                  >
                    None
                  </Button>
                </div>
              </div>
              {group.selections.map(({ reference, selection }) => (
                <ToggleInfoRow
                  key={selection}
                  label={reference}
                  checked={selected.has(selection)}
                  disabled={disabled}
                  testId={`judge-skill-reference-${selection}`}
                  onChange={(next) =>
                    onChange(
                      next
                        ? [...selectedSkillReferences, selection]
                        : selectedSkillReferences.filter(
                            (entry) => entry !== selection
                          )
                    )
                  }
                />
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
