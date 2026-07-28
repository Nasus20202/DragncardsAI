import { describe, expect, it } from "vitest";

import {
  filterMentionableSkills,
  findSkillMention,
  removeSkillMention,
} from "@/features/play/lib/skill-mentions";
import { SkillDefinitionResponse } from "@/features/shared/lib/types";

const skills: SkillDefinitionResponse[] = [
  {
    name: "marvel-champions-play",
    path: "/skills/marvel-champions-play",
    description: "Play Marvel Champions",
    metadata: {},
  },
  {
    name: "board-reader",
    path: "/skills/board-reader",
    description: "Read the board",
    metadata: {},
  },
];

describe("findSkillMention", () => {
  it("finds a mention that starts the message", () => {
    expect(findSkillMention("@mar", 4)).toEqual({
      start: 0,
      end: 4,
      query: "mar",
    });
  });

  it("finds a mention that follows whitespace", () => {
    expect(findSkillMention("play the villain phase @mar", 27)).toEqual({
      start: 23,
      end: 27,
      query: "mar",
    });
  });

  it("treats a bare trigger as an empty query", () => {
    expect(findSkillMention("@", 1)).toEqual({ start: 0, end: 1, query: "" });
  });

  it("ignores a trigger inside a word", () => {
    expect(findSkillMention("mail@example.com", 16)).toBeNull();
  });

  it("ignores a trigger inside a mention token", () => {
    expect(findSkillMention("@a@b", 4)).toBeNull();
  });

  it("ends a mention at whitespace", () => {
    expect(findSkillMention("@mar vel", 8)).toBeNull();
  });

  it("reads only up to the caret", () => {
    expect(findSkillMention("@marvel", 4)).toEqual({
      start: 0,
      end: 4,
      query: "mar",
    });
  });

  it("finds nothing when the caret sits before the trigger", () => {
    expect(findSkillMention("@mar", 0)).toBeNull();
  });

  it("finds nothing in text without a trigger", () => {
    expect(findSkillMention("play the villain phase", 22)).toBeNull();
  });
});

describe("removeSkillMention", () => {
  it("drops the token and reports the resulting caret", () => {
    expect(
      removeSkillMention("play @mar", { start: 5, end: 9, query: "mar" })
    ).toEqual({ text: "play ", caret: 5 });
  });

  it("keeps the text that follows the caret", () => {
    expect(
      removeSkillMention("@mar now", { start: 0, end: 4, query: "mar" })
    ).toEqual({ text: " now", caret: 0 });
  });
});

describe("filterMentionableSkills", () => {
  it("offers every unattached skill for an empty query", () => {
    expect(filterMentionableSkills(skills, "", [])).toEqual(skills);
  });

  it("matches on a case-insensitive substring of the name", () => {
    expect(filterMentionableSkills(skills, "BOARD", [])).toEqual([skills[1]]);
  });

  it("excludes skills already attached to the session", () => {
    expect(filterMentionableSkills(skills, "", ["board-reader"])).toEqual([
      skills[0],
    ]);
  });

  it("returns nothing when no unattached skill matches", () => {
    expect(filterMentionableSkills(skills, "nonesuch", [])).toEqual([]);
  });
});
