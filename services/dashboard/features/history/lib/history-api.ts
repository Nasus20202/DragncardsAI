import { readJson } from "@/features/history/lib/http";
import {
  HistoryDeleteResponse,
  HistoryEvent,
  HistoryGame,
  HistoryImportResult,
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

/** One page of a game's timeline, plus the cursor to fetch the next one. */
export interface HistoryEventPage {
  events: HistoryEvent[];
  /** Pass as `afterSeq` to fetch the next page; null when the log is exhausted. */
  nextAfterSeq: number | null;
}

/**
 * The largest page the history-service will serve (`limit` is capped at 1000
 * server-side, which bounds per-request database work and response size).
 */
export const HISTORY_PAGE_LIMIT = 1000;

/**
 * A safety bound on how much of one game's timeline the browser will hold. It
 * is far above any realistic game, but it must exist so a pathological log
 * cannot hang the tab — and when it is hit the UI has to say so rather than
 * look complete (see `useHistory`'s `truncated`).
 */
export const HISTORY_MAX_EVENTS = 20_000;

export async function listHistoryEventPage(
  gameId: string,
  options?: { afterSeq?: number; limit?: number }
): Promise<HistoryEventPage> {
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
  const payload = await readJson<
    { events?: HistoryEvent[]; next_after_seq?: number | null } | HistoryEvent[]
  >(response);
  if (Array.isArray(payload)) {
    return { events: payload, nextAfterSeq: null };
  }
  return {
    events: payload.events ?? [],
    nextAfterSeq: payload.next_after_seq ?? null,
  };
}

/** A game's complete timeline, and whether the safety bound cut it short. */
export interface HistoryTimeline {
  events: HistoryEvent[];
  /** True when `HISTORY_MAX_EVENTS` stopped the walk before the log ended. */
  truncated: boolean;
}

/**
 * Every event for a game, following the `after_seq` cursor page by page until
 * the history-service reports the log is exhausted. The endpoint defaults to
 * only 100 events per request, so a single call shows a fraction of a real
 * game; the cursor is the API's own answer to that. Mirrors the server-side
 * precedent in `eval-service`'s `HistoryClient.list_all_events`.
 */
export async function listAllHistoryEvents(
  gameId: string,
  options?: { pageLimit?: number; maxEvents?: number }
): Promise<HistoryTimeline> {
  const pageLimit = options?.pageLimit ?? HISTORY_PAGE_LIMIT;
  const maxEvents = options?.maxEvents ?? HISTORY_MAX_EVENTS;
  const events: HistoryEvent[] = [];
  let afterSeq = 0;
  for (;;) {
    const page = await listHistoryEventPage(gameId, {
      afterSeq,
      limit: pageLimit,
    });
    events.push(...page.events);
    if (page.nextAfterSeq === null || page.events.length === 0) {
      return { events, truncated: false };
    }
    if (events.length >= maxEvents) {
      return { events, truncated: true };
    }
    afterSeq = page.nextAfterSeq;
  }
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

/**
 * The URL that downloads a game's whole recorded history as an NDJSON bundle.
 * Points at `GET /api/proxy/history/games/{game_id}/export`, which answers with
 * a `Content-Disposition: attachment` filename — so this is navigated to (or
 * given to an anchor) rather than fetched and buffered, keeping a bundle that
 * can run to tens of megabytes out of the tab's memory.
 */
export function historyExportUrl(gameId: string): string {
  return `/api/proxy/history/games/${encodeURIComponent(gameId)}/export`;
}

/**
 * Import an NDJSON history bundle. Calls `POST /api/proxy/history/import`,
 * streaming the picked file as the request body. `gameId` chooses the target
 * game; omitting it lands the history under the `game_id` recorded in the
 * bundle. Rejects with the service's own message (which names the offending
 * line) when the bundle is malformed, oversized, or the target already exists.
 */
export async function importHistoryBundle(
  file: File,
  options?: { gameId?: string }
): Promise<HistoryImportResult> {
  const params = new URLSearchParams();
  if (options?.gameId) {
    params.set("game_id", options.gameId);
  }
  const query = params.toString();
  const response = await fetch(
    `/api/proxy/history/import${query ? `?${query}` : ""}`,
    {
      method: "POST",
      headers: { "content-type": "application/x-ndjson" },
      body: file,
    }
  );
  return readJson<HistoryImportResult>(response);
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
