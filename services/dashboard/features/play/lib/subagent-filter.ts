import { SubagentEntry } from "@/features/play/lib/play-session-events";

/**
 * The status axis the subagent list filters on, in the order the control offers
 * it. Status is the axis because the complaint the filter answers is that
 * *finished* subagents crowd out the ones still doing something.
 */
export const SUBAGENT_STATUS_FILTERS = [
  { key: "all", label: "All" },
  { key: "running", label: "Live" },
  { key: "completed", label: "Done" },
  { key: "failed", label: "Failed" },
] as const;

export type SubagentStatusFilter =
  (typeof SUBAGENT_STATUS_FILTERS)[number]["key"];

export const DEFAULT_SUBAGENT_STATUS_FILTER: SubagentStatusFilter = "all";

export function isSubagentStatusFilter(
  value: unknown
): value is SubagentStatusFilter {
  return SUBAGENT_STATUS_FILTERS.some((option) => option.key === value);
}

/** The entries a status filter admits. `all` admits every entry, in order. */
export function filterSubagentsByStatus(
  entries: SubagentEntry[],
  filter: SubagentStatusFilter
): SubagentEntry[] {
  if (filter === "all") {
    return entries;
  }
  return entries.filter((entry) => entry.status === filter);
}

/** How many entries each filter would show, for the counts on the control. */
export function countSubagentsByStatus(
  entries: SubagentEntry[]
): Record<SubagentStatusFilter, number> {
  const counts: Record<SubagentStatusFilter, number> = {
    all: entries.length,
    running: 0,
    completed: 0,
    failed: 0,
  };
  for (const entry of entries) {
    counts[entry.status] += 1;
  }
  return counts;
}

/**
 * The entries worth showing when the list is collapsed: the ones still working
 * and the ones that went wrong. A subagent that finished cleanly needs nothing
 * from the reader, which is precisely why it should not be occupying the corner
 * of the transcript.
 */
export function attentionSubagents(entries: SubagentEntry[]): SubagentEntry[] {
  return entries.filter(
    (entry) => entry.status === "running" || entry.status === "failed"
  );
}
