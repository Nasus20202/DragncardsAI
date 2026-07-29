import { describe, expect, it } from "vitest";
import { SubagentEntry } from "@/features/play/lib/play-session-events";
import {
  DEFAULT_SUBAGENT_STATUS_FILTER,
  SUBAGENT_STATUS_FILTERS,
  attentionSubagents,
  countSubagentsByStatus,
  filterSubagentsByStatus,
  isSubagentStatusFilter,
} from "@/features/play/lib/subagent-filter";

function entry(id: string, status: SubagentEntry["status"]): SubagentEntry {
  return { childJobId: id, childSessionId: `${id}-session`, status };
}

const entries = [
  entry("a", "completed"),
  entry("b", "running"),
  entry("c", "failed"),
  entry("d", "completed"),
];

describe("subagent status filter options", () => {
  it("offers one option per status plus an unfiltered one", () => {
    expect(SUBAGENT_STATUS_FILTERS.map((option) => option.key)).toEqual([
      "all",
      "running",
      "completed",
      "failed",
    ]);
  });

  it("defaults to showing everything", () => {
    expect(DEFAULT_SUBAGENT_STATUS_FILTER).toBe("all");
  });

  it("recognises only the offered keys", () => {
    expect(isSubagentStatusFilter("failed")).toBe(true);
    expect(isSubagentStatusFilter("all")).toBe(true);
    expect(isSubagentStatusFilter("cancelled")).toBe(false);
    expect(isSubagentStatusFilter(undefined)).toBe(false);
    expect(isSubagentStatusFilter(3)).toBe(false);
  });
});

describe("filterSubagentsByStatus", () => {
  it("returns every entry, in order, for `all`", () => {
    expect(filterSubagentsByStatus(entries, "all")).toBe(entries);
  });

  it("returns only the entries of the chosen status", () => {
    expect(
      filterSubagentsByStatus(entries, "completed").map((e) => e.childJobId)
    ).toEqual(["a", "d"]);
    expect(
      filterSubagentsByStatus(entries, "running").map((e) => e.childJobId)
    ).toEqual(["b"]);
    expect(
      filterSubagentsByStatus(entries, "failed").map((e) => e.childJobId)
    ).toEqual(["c"]);
  });

  it("returns nothing when no entry holds the chosen status", () => {
    expect(
      filterSubagentsByStatus([entry("a", "completed")], "failed")
    ).toEqual([]);
  });

  it("preserves the given order within a status", () => {
    const many = [
      entry("first", "completed"),
      entry("second", "completed"),
      entry("third", "completed"),
    ];
    expect(
      filterSubagentsByStatus(many, "completed").map((e) => e.childJobId)
    ).toEqual(["first", "second", "third"]);
  });
});

describe("countSubagentsByStatus", () => {
  it("counts each status and the whole list", () => {
    expect(countSubagentsByStatus(entries)).toEqual({
      all: 4,
      running: 1,
      completed: 2,
      failed: 1,
    });
  });

  it("reports zeroes for an empty list", () => {
    expect(countSubagentsByStatus([])).toEqual({
      all: 0,
      running: 0,
      completed: 0,
      failed: 0,
    });
  });

  it("agrees with the filter it labels", () => {
    const counts = countSubagentsByStatus(entries);
    for (const option of SUBAGENT_STATUS_FILTERS) {
      expect(filterSubagentsByStatus(entries, option.key)).toHaveLength(
        counts[option.key]
      );
    }
  });
});

describe("attentionSubagents", () => {
  it("keeps the running and the failed and drops the finished", () => {
    expect(attentionSubagents(entries).map((e) => e.childJobId)).toEqual([
      "b",
      "c",
    ]);
  });

  it("is empty once everything has finished cleanly", () => {
    expect(
      attentionSubagents([entry("a", "completed"), entry("b", "completed")])
    ).toEqual([]);
  });
});
