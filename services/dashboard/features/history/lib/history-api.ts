import { readJson } from "@/features/history/lib/http";
import {
  HistoryDeleteResponse,
  HistoryEvent,
  HistoryExportMode,
  HistoryGame,
  HistoryImportResult,
  HistorySnapshot,
  GamePlatform,
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
  gameId: string,
  platform: GamePlatform = "dragncards"
): Promise<HistoryDeleteResponse> {
  const query = platform === "marvel-lcg" ? "?platform=marvel-lcg" : "";
  const response = await fetch(
    `/api/proxy/history/games/${encodeURIComponent(gameId)}${query}`,
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
 * The largest *timeline* page the history-service will serve. It is higher than
 * the events read's ceiling of 1000 because a timeline entry is a few hundred
 * bytes rather than a few hundred kilobytes: that endpoint omits the raw
 * DragnCards state and the agent conversation from each payload.
 */
export const HISTORY_TIMELINE_PAGE_LIMIT = 5000;

/**
 * A safety bound on how much of one game's timeline the browser will hold. It
 * is far above any realistic game, but it must exist so a pathological log
 * cannot hang the tab — and when it is hit the UI has to say so rather than
 * look complete (see `useHistory`'s `truncated`).
 */
export const HISTORY_MAX_EVENTS = 20_000;

async function fetchEventPage(
  gameId: string,
  resource: "events" | "timeline",
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
    `/api/proxy/history/games/${encodeURIComponent(gameId)}/${resource}${
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

export async function listHistoryEventPage(
  gameId: string,
  options?: { afterSeq?: number; limit?: number }
): Promise<HistoryEventPage> {
  return fetchEventPage(gameId, "events", options);
}

/**
 * One page of a game's *timeline*: the same cursor contract and the same event
 * shape as {@link listHistoryEventPage}, but with each payload's unbounded
 * fields omitted server-side. This is what the history view lists; a single
 * event's complete payload comes from {@link fetchHistoryEvent}.
 */
export async function listHistoryTimelinePage(
  gameId: string,
  options?: { afterSeq?: number; limit?: number }
): Promise<HistoryEventPage> {
  return fetchEventPage(gameId, "timeline", options);
}

/**
 * One event with its payload intact, addressed by `seq`. The events read has no
 * by-seq route, but its cursor is exclusive, so the single-event window is
 * `after_seq = seq - 1, limit = 1`. Resolves to null when the seq is not there.
 */
export async function fetchHistoryEvent(
  gameId: string,
  seq: number
): Promise<HistoryEvent | null> {
  const page = await listHistoryEventPage(gameId, {
    afterSeq: Math.max(0, seq - 1),
    limit: 1,
  });
  const event = page.events[0];
  return event && event.seq === seq ? event : null;
}

/** A game's complete timeline, and whether the safety bound cut it short. */
export interface HistoryTimeline {
  events: HistoryEvent[];
  /** True when `HISTORY_MAX_EVENTS` stopped the walk before the log ended. */
  truncated: boolean;
}

/**
 * A game's whole timeline, following the `after_seq` cursor page by page until
 * the history-service reports the log is exhausted. Mirrors the server-side
 * precedent in `eval-service`'s `HistoryClient.list_all_events`.
 *
 * Reads the timeline resource rather than the events resource on purpose. The
 * events read carries every payload in full, and a recorded DragnCards state is
 * ~450-470 KB, so a few hundred events is tens of megabytes and several seconds
 * on the server before a byte reaches the browser — measured at 4.3 s and 86 MiB
 * for a 400-event game. The same walk over timeline entries is 0.6 s and 262
 * KiB, which is what makes loading the index of a game affordable enough to keep
 * doing it. Each event's full payload is fetched only when something needs it
 * (see {@link fetchHistoryEvent}).
 *
 * `afterSeq` resumes an earlier walk: history is append-only, so a refresh only
 * has to ask for what was recorded after the highest entry already held.
 */
export async function listAllHistoryTimeline(
  gameId: string,
  options?: { pageLimit?: number; maxEvents?: number; afterSeq?: number }
): Promise<HistoryTimeline> {
  const pageLimit = options?.pageLimit ?? HISTORY_TIMELINE_PAGE_LIMIT;
  const maxEvents = options?.maxEvents ?? HISTORY_MAX_EVENTS;
  const events: HistoryEvent[] = [];
  let afterSeq = options?.afterSeq ?? 0;
  for (;;) {
    const page = await listHistoryTimelinePage(gameId, {
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
 *
 * The mode is always sent, including the `full` default, so the request says
 * which of the two bundles it wants instead of relying on the server's choice of
 * default staying what it is today.
 */
export function historyExportUrl(
  gameId: string,
  mode: HistoryExportMode = "full"
): string {
  const query = new URLSearchParams({ mode }).toString();
  return `/api/proxy/history/games/${encodeURIComponent(gameId)}/export?${query}`;
}

/**
 * The filename the export endpoint puts in its `Content-Disposition` header,
 * mirroring the history-service's own `bundle_filename`. An anchor's `download`
 * attribute overrides the header for a same-origin response, so the two have to
 * agree or the same game downloads under two different names depending on how it
 * was fetched. The mode is part of the name so exporting a game both ways does
 * not silently overwrite one file with the other.
 */
export function historyExportFilename(
  gameId: string,
  mode: HistoryExportMode = "full"
): string {
  return `dragncards-history-${gameId}-${mode}.ndjson`;
}

/**
 * Import an NDJSON history bundle. Calls `POST /api/proxy/history/import`,
 * streaming the picked file as the request body.
 *
 * Three targets, in the order the service resolves them: `gameId` names one
 * outright; `asNew` asks the service to mint a fresh uuid4, which is the only
 * target that cannot collide with an existing game; and passing neither lands
 * the history under the `game_id` recorded in the bundle's own header. Asking
 * for both a named target and a new one is a 400 — they are two answers to one
 * question — so callers offer them as a single choice.
 *
 * Rejects with the service's own message (which names the offending line) when
 * the bundle is malformed or oversized, and with its 409 when the chosen target
 * already has recorded history.
 */
export async function importHistoryBundle(
  file: File,
  options?: { gameId?: string; asNew?: boolean }
): Promise<HistoryImportResult> {
  const params = new URLSearchParams();
  if (options?.gameId) {
    params.set("game_id", options.gameId);
  }
  if (options?.asNew) {
    params.set("as_new", "true");
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
