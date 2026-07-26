import { readJson } from "@/features/history/lib/http";
import {
  HistoryDeleteResponse,
  HistoryEvent,
  HistoryGame,
  HistorySnapshot,
  RestoreOutcome,
  RestoreRequestBody,
} from "@/features/shared/lib/types";

/**
 * List games that have recorded history, ordered by most-recent activity.
 * Calls `GET /api/proxy/history/games`.
 */
export async function listHistoryGames(): Promise<HistoryGame[]> {
  const response = await fetch("/api/proxy/history/games", {
    cache: "no-store",
  });
  const payload = await readJson<{ games?: HistoryGame[] } | HistoryGame[]>(
    response
  );
  return Array.isArray(payload) ? payload : (payload.games ?? []);
}

/**
 * Delete ALL recorded history for a game (events + snapshots + bookkeeping).
 * Calls `DELETE /api/proxy/history/games/{game_id}`. Idempotent.
 */
export async function deleteHistoryGame(
  gameId: string
): Promise<HistoryDeleteResponse> {
  const response = await fetch(
    `/api/proxy/history/games/${encodeURIComponent(gameId)}`,
    { method: "DELETE" }
  );
  return readJson<HistoryDeleteResponse>(response);
}

export async function listHistoryEvents(
  gameId: string,
  options?: { afterSeq?: number; limit?: number }
): Promise<HistoryEvent[]> {
  const params = new URLSearchParams();
  if (options?.afterSeq !== undefined) {
    params.set("after_seq", String(options.afterSeq));
  }
  if (options?.limit !== undefined) {
    params.set("limit", String(options.limit));
  }
  const query = params.toString();
  const response = await fetch(
    `/api/proxy/history/games/${encodeURIComponent(gameId)}/events${
      query ? `?${query}` : ""
    }`,
    { cache: "no-store" }
  );
  const payload = await readJson<{ events?: HistoryEvent[] } | HistoryEvent[]>(
    response
  );
  return Array.isArray(payload) ? payload : (payload.events ?? []);
}

export async function listHistorySnapshots(
  gameId: string
): Promise<HistorySnapshot[]> {
  const response = await fetch(
    `/api/proxy/history/games/${encodeURIComponent(gameId)}/snapshots`,
    { cache: "no-store" }
  );
  const payload = await readJson<
    { snapshots?: HistorySnapshot[] } | HistorySnapshot[]
  >(response);
  return Array.isArray(payload) ? payload : (payload.snapshots ?? []);
}

export async function restoreGame(
  gameId: string,
  body: RestoreRequestBody
): Promise<RestoreOutcome> {
  const response = await fetch(
    `/api/proxy/history/games/${encodeURIComponent(gameId)}/restore`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }
  );
  return readJson<RestoreOutcome>(response);
}

/**
 * Delete a live game-service session. Used to tear down the ephemeral
 * reconstruction session an `ephemeral` restore creates. Calls
 * `DELETE /api/proxy/game/games/{id}`. Best-effort: resolves on any response
 * (the session may already be gone, or reaped server-side by TTL).
 */
export async function deleteGameSession(sessionId: string): Promise<void> {
  await fetch(`/api/proxy/game/games/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}

/**
 * Dispose an ephemeral reconstruction session using a transport that survives
 * page unload (`fetch` with `keepalive`). The ephemeral session is
 * non-emitting, so only the game-service session needs deleting — no history
 * cleanup. This is the FAST PATH only: correctness does not depend on it, a
 * server-side TTL reaper handles lost connections. Synchronous-friendly:
 * callers in `pagehide`/`visibilitychange` must not await it.
 */
export function disposeReconstructionViaBeacon(sessionId: string): void {
  // `navigator.sendBeacon` only issues POSTs, and our proxy routes the method
  // through verbatim — so a beacon cannot express DELETE. Use keepalive fetch,
  // which is honored during unload by modern browsers.
  try {
    void fetch(`/api/proxy/game/games/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
      keepalive: true,
    });
  } catch {
    /* unload teardown is best-effort; the TTL reaper is the safety net */
  }
}
