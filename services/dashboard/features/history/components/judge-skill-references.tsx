"use client";

import { SkillDefinitionResponse } from "@/features/shared/lib/types";
import { ToggleInfoRow } from "@/features/shared/components/toggle-info-row";

export interface JudgeSkillReferencesProps {
  skills: SkillDefinitionResponse[];
  selectedSkills: string[];
  selectedSkillReferences: string[];
  disabled?: boolean;
  onChange: (nextSelectedSkillReferences: string[]) => void;
}

/**
 * Mirrors `MAX_SKILL_REFERENCES` in the eval-service request schema. The server
 * rejects a ninth selection with a 422, and `marvel-champions-rules-reference`
 * ships 21 reference files -- so ticking a ninth is a normal-looking action, not
 * an absurd one. Stop it here rather than letting the user find the limit out
 * from a failed evaluation.
 */
export const MAX_SKILL_REFERENCES = 8;

/**
 * Reference-file toggles for the skills the judge has been given, grouped per
 * skill. A skill only appears once it is selected AND it ships reference files,
 * so the section stays empty (renders nothing) until there is something to pick.
 *
 * Each toggle's value is the full `"<skill-name>/<relative-path>.md"` selection
 * string the eval-service expects in `judge.skill_references`.
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
      references: skill.references ?? [],
    }));

  if (groups.length === 0) {
    return null;
  }

  const atLimit = selectedSkillReferences.length >= MAX_SKILL_REFERENCES;

  return (
    <div className="grid gap-2" data-testid="judge-skill-references">
      <p className="text-xs font-semibold uppercase tracking-wider text-default-400">
        Skill references
        <span className="ml-2 normal-case tracking-normal text-default-300">
          {selectedSkillReferences.length}/{MAX_SKILL_REFERENCES}
        </span>
      </p>
      <div className="grid gap-2 rounded-lg border border-default-200/60 px-3 py-2">
        {groups.map((group) => (
          <div key={group.name} className="grid gap-1">
            <p className="text-[11px] font-medium text-default-400">
              {group.name}
            </p>
            {group.references.map((reference) => {
              const selection = `${group.name}/${reference}`;
              const checked = selectedSkillReferences.includes(selection);
              return (
                <ToggleInfoRow
                  key={selection}
                  label={reference}
                  checked={checked}
                  // At the limit, only the already-selected rows stay live, so
                  // the user can always swap one choice for another.
                  disabled={disabled || (atLimit && !checked)}
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
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
