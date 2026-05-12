import { JobDetail } from "@/features/shared/lib/types";

export interface SubagentEntry {
  childJobId: string;
  childSessionId: string;
  status: "running" | "completed" | "failed";
  name?: string;
  reason?: string;
}

/**
 * Derive subagent entries from parent job events.
 *
 * @param jobs - All jobs for the parent session.
 * @param childJobStatuses - Optional map of child job ID → DB status string.
 *   Used to reconcile entries that appear "running" in parent events but are
 *   already terminal in the DB (e.g. after a worker restart where
 *   subagent_completed / subagent_failed was never written).
 */
export function deriveSubagentEntries(
  jobs: JobDetail[],
  childJobStatuses?: Map<string, string>
): SubagentEntry[] {
  const byId = new Map<string, SubagentEntry>();
  for (const job of jobs) {
    for (const event of job.events) {
      const payload = event.payload as Record<string, unknown>;
      const childJobId =
        typeof payload.child_job_id === "string" ? payload.child_job_id : null;
      if (!childJobId) {
        continue;
      }

      const childSessionId =
        typeof payload.child_session_id === "string"
          ? payload.child_session_id
          : "";
      const name = typeof payload.name === "string" ? payload.name : undefined;
      if (event.event_type === "subagent_started") {
        if (!byId.has(childJobId)) {
          byId.set(childJobId, {
            childJobId,
            childSessionId,
            status: "running",
            name,
          });
        }
        continue;
      }

      const existing = byId.get(childJobId);
      if (!existing) {
        continue;
      }

      if (event.event_type === "subagent_completed") {
        byId.set(childJobId, { ...existing, status: "completed" });
      }

      if (event.event_type === "subagent_failed") {
        byId.set(childJobId, {
          ...existing,
          status: "failed",
          reason:
            typeof payload.reason === "string"
              ? payload.reason
              : existing.reason,
        });
      }
    }
  }

  // Reconcile any entries still "running" against actual child job DB status.
  if (childJobStatuses) {
    for (const [childJobId, entry] of byId) {
      if (entry.status !== "running") continue;
      const dbStatus = childJobStatuses.get(childJobId);
      if (!dbStatus || dbStatus === "queued" || dbStatus === "running")
        continue;
      byId.set(childJobId, {
        ...entry,
        status: dbStatus === "completed" ? "completed" : "failed",
      });
    }
  }

  return Array.from(byId.values());
}
