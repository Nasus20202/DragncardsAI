import { JobSummary } from "@/features/shared/lib/types";

export function compareJobsOldestFirst(left: JobSummary, right: JobSummary) {
  return new Date(left.created_at).getTime() - new Date(right.created_at).getTime();
}
