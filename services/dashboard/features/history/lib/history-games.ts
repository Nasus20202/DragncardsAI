import { SessionSummary } from "@/features/shared/lib/types";

/**
 * game_id -> friendly session name, from orchestrator sessions whose
 * `metadata.game_id` links back to a history game. First (most recent) name
 * for a game_id wins.
 */
export function mapSessionGameNames(
  sessions: SessionSummary[]
): Record<string, string> {
  const names: Record<string, string> = {};
  for (const session of sessions) {
    const gid = session.metadata?.game_id;
    if (typeof gid === "string" && gid && session.name) {
      names[gid] ??= session.name;
    }
  }
  return names;
}

/** Human-readable absolute timestamp for a recorded-at ISO string. */
export function formatActivity(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString();
}
