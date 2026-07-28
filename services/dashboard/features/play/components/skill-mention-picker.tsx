"use client";

import { SkillDefinitionResponse } from "@/features/shared/lib/types";

/**
 * The list the composer's `@` mention opens: the skills that can still be
 * attached to the session, one highlighted for keyboard selection.
 *
 * Focus deliberately stays in the prompt textarea — the user is mid-sentence —
 * so this is a plain `listbox`/`option` structure the textarea points at with
 * `aria-activedescendant` rather than a focus-managing HeroUI overlay, and the
 * options suppress the default mousedown so clicking one does not blur the
 * textarea. Styling matches the workspace's other floating panels.
 */
export function SkillMentionPicker({
  id,
  skills,
  highlightedIndex,
  onSelect,
}: {
  /** Owning id; each option's DOM id is derived from it. */
  id: string;
  skills: SkillDefinitionResponse[];
  highlightedIndex: number;
  onSelect: (skillName: string) => void;
}) {
  return (
    <div
      className="absolute bottom-full left-2 z-30 mb-1 w-full max-w-xs overflow-hidden rounded-lg border border-default-200 bg-content1/95 shadow-lg backdrop-blur-sm sm:left-4"
      data-testid="skill-mention-picker"
    >
      <p className="px-2.5 pt-2 text-[10px] font-semibold uppercase tracking-wider text-default-400">
        Skills
      </p>
      <div
        aria-label="Attach a skill"
        className="max-h-56 overflow-y-auto py-1"
        id={id}
        role="listbox"
      >
        {skills.map((skill, index) => (
          <button
            aria-selected={index === highlightedIndex}
            className={[
              "flex w-full flex-col items-start gap-0.5 px-2.5 py-1.5 text-left",
              index === highlightedIndex ? "bg-default-100" : "",
            ].join(" ")}
            data-testid={`skill-mention-option-${skill.name}`}
            id={skillMentionOptionId(id, skill.name)}
            key={skill.name}
            role="option"
            type="button"
            // Keep the caret in the textarea: the click must not move focus.
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => onSelect(skill.name)}
          >
            <span className="text-xs text-foreground">{skill.name}</span>
            {skill.description && (
              <span className="line-clamp-2 text-[11px] text-default-400">
                {skill.description}
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

/** DOM id of one option, for the textarea's `aria-activedescendant`. */
export function skillMentionOptionId(pickerId: string, skillName: string) {
  return `${pickerId}-${skillName}`;
}
