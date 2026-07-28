import { filterComboSelectItems } from "@/features/shared/components/combo-select";
import { SkillDefinitionResponse } from "@/features/shared/lib/types";

/**
 * Parsing for the chat composer's `@` skill mentions.
 *
 * A mention is part of the message: choosing a skill completes the token into
 * `@<skill-name>` and leaves it in the prompt, because that token is what loads
 * the skill's instructions into the turn being sent. It also attaches the skill
 * to the session — the chip row and the settings panel's toggles show that half
 * — so the two readings of "attached" stay visible at once.
 *
 * Nothing here talks to the orchestrator: the composer's owner performs the
 * skill assignment, and the submit path names the mentioned skills so the
 * orchestrator can load their content server-side.
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
 * The message text with the partial mention completed to `@<skillName> `, plus
 * the caret position that leaves behind.
 *
 * The token stays in the message: it is what tells the orchestrator to load that
 * skill into this turn, and it is what the user sees they pulled in. The
 * trailing space is added only when the text does not already continue with
 * whitespace, so completing mid-sentence does not double the gap.
 */
export function completeSkillMention(
  text: string,
  mention: SkillMention,
  skillName: string
): { text: string; caret: number } {
  const rest = text.slice(mention.end);
  const token =
    SKILL_MENTION_TRIGGER + skillName + (/^\s/.test(rest) ? "" : " ");
  return {
    text: text.slice(0, mention.start) + token + rest,
    caret: mention.start + token.length,
  };
}

/**
 * The known skills a message mentions, in first-mention order and without
 * repeats.
 *
 * Only a token that matches a known skill name exactly counts, so prose
 * containing an `@` — an address, a handle, a half-typed name the user gave up
 * on — loads nothing. Mention boundaries match {@link findSkillMention}: the
 * trigger opens a mention at the start of the text or after whitespace, and the
 * token ends at the first whitespace.
 */
export function findMentionedSkillNames(
  text: string,
  knownSkillNames: string[]
): string[] {
  const known = new Set(knownSkillNames);
  const mentioned: string[] = [];
  for (const match of text.matchAll(/(?:^|\s)@([^\s@]+)/g)) {
    const name = match[1];
    if (known.has(name) && !mentioned.includes(name)) {
      mentioned.push(name);
    }
  }
  return mentioned;
}

/**
 * The skills a mention should offer: every skill available to the session,
 * narrowed by the mention's query.
 *
 * A skill already attached to the session is still offered, because a mention
 * loads that skill's instructions into *this* message — something worth doing
 * again on a later turn, unlike the session attachment, which is already done.
 *
 * Filtering reuses the shared searchable picker's match so the mention picker
 * and the model picker narrow their lists the same way.
 */
export function filterMentionableSkills(
  skills: SkillDefinitionResponse[],
  query: string
): SkillDefinitionResponse[] {
  const matched = new Set(
    filterComboSelectItems(
      skills.map((skill) => ({ value: skill.name, label: skill.name })),
      query
    ).map((item) => item.value)
  );
  return skills.filter((skill) => matched.has(skill.name));
}
