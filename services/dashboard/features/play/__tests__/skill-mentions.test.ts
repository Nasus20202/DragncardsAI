import { describe, expect, it } from "vitest";

import {
  completeSkillMention,
  filterMentionableSkills,
  findMentionedSkillNames,
  findSkillMention,
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

describe("completeSkillMention", () => {
  it("completes the token and reports the caret after it", () => {
    expect(
      completeSkillMention(
        "play @mar",
        { start: 5, end: 9, query: "mar" },
        "marvel-champions-play"
      )
    ).toEqual({ text: "play @marvel-champions-play ", caret: 28 });
  });

  it("keeps the text that follows the caret", () => {
    expect(
      completeSkillMention(
        "@mar now",
        { start: 0, end: 4, query: "mar" },
        "board-reader"
      )
    ).toEqual({ text: "@board-reader now", caret: 13 });
  });

  it("completes a bare trigger", () => {
    expect(
      completeSkillMention("@", { start: 0, end: 1, query: "" }, "board-reader")
    ).toEqual({ text: "@board-reader ", caret: 14 });
  });
});

describe("findMentionedSkillNames", () => {
  const known = ["marvel-champions-play", "board-reader"];

  it("finds a mention that starts the message", () => {
    expect(findMentionedSkillNames("@board-reader go", known)).toEqual([
      "board-reader",
    ]);
  });

  it("finds a mention at the end of the message", () => {
    expect(findMentionedSkillNames("go @board-reader", known)).toEqual([
      "board-reader",
    ]);
  });

  it("keeps first-mention order and drops repeats", () => {
    expect(
      findMentionedSkillNames(
        "@board-reader then @marvel-champions-play then @board-reader",
        known
      )
    ).toEqual(["board-reader", "marvel-champions-play"]);
  });

  it("ignores a token that matches no known skill", () => {
    expect(findMentionedSkillNames("@nonesuch go", known)).toEqual([]);
  });

  it("ignores a trigger inside a word", () => {
    expect(findMentionedSkillNames("mail@board-reader", known)).toEqual([]);
  });

  it("finds nothing in text without a mention", () => {
    expect(findMentionedSkillNames("play the villain phase", known)).toEqual(
      []
    );
  });
});

describe("filterMentionableSkills", () => {
  it("offers every available skill for an empty query", () => {
    expect(filterMentionableSkills(skills, "")).toEqual(skills);
  });

  it("matches on a case-insensitive substring of the name", () => {
    expect(filterMentionableSkills(skills, "BOARD")).toEqual([skills[1]]);
  });

  it("returns nothing when no skill matches", () => {
    expect(filterMentionableSkills(skills, "nonesuch")).toEqual([]);
  });
});
