import { filterComboSelectItems } from "@/features/shared/components/combo-select";
import { SkillDefinitionResponse } from "@/features/shared/lib/types";

/**
 * Parsing for the chat composer's `@` skill mentions.
 *
 * A mention is only an input gesture: choosing a skill attaches it to the
 * session and the token is removed from the message, because the attached skill
 * is then shown as a chip on the composer rather than as prose in the prompt.
 * Nothing here talks to the orchestrator — the composer's owner performs the
 * same skill assignment the settings panel's toggles drive.
 */

/** The character that opens the picker. */
export const SKILL_MENTION_TRIGGER = "@";

export interface SkillMention {
  /** Index of the trigger character in the message text. */
  start: number;
  /** Exclusive end of the token — the caret position that produced it. */
  end: number;
  /** What the user has typed after the trigger, possibly empty. */
  query: string;
}

/**
 * The mention the caret currently sits in, or `null` when there is none.
 *
 * A trigger only opens a mention at the start of the message or after
 * whitespace, so an email address does not, and the token ends at the first
 * whitespace, so a finished word does not keep the picker open.
 */
export function findSkillMention(
  text: string,
  caret: number
): SkillMention | null {
  const before = text.slice(0, caret);
  const start = before.lastIndexOf(SKILL_MENTION_TRIGGER);
  if (start < 0) {
    return null;
  }

  const preceding = start === 0 ? "" : before[start - 1];
  if (preceding !== "" && !/\s/.test(preceding)) {
    return null;
  }

  const query = before.slice(start + 1);
  if (/[\s@]/.test(query)) {
    return null;
  }

  return { start, end: caret, query };
}

/**
 * The message text with the mention token removed, plus the caret position it
 * leaves behind.
 */
export function removeSkillMention(
  text: string,
  mention: SkillMention
): { text: string; caret: number } {
  return {
    text: text.slice(0, mention.start) + text.slice(mention.end),
    caret: mention.start,
  };
}

/**
 * The skills a mention should offer: those not already attached to the session,
 * narrowed by the mention's query.
 *
 * Filtering reuses the shared searchable picker's match so the mention picker
 * and the model picker narrow their lists the same way.
 */
export function filterMentionableSkills(
  skills: SkillDefinitionResponse[],
  query: string,
  attachedSkills: string[]
): SkillDefinitionResponse[] {
  const attached = new Set(attachedSkills);
  const candidates = skills.filter((skill) => !attached.has(skill.name));
  const matched = new Set(
    filterComboSelectItems(
      candidates.map((skill) => ({ value: skill.name, label: skill.name })),
      query
    ).map((item) => item.value)
  );
  return candidates.filter((skill) => matched.has(skill.name));
}
