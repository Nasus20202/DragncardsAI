import { afterEach, describe, expect, it, vi } from "vitest";

import {
  deleteHistoryGame,
  listAllHistoryEvents,
  listHistoryEventPage,
  listHistoryGames,
  listHistorySnapshots,
  restoreGame,
} from "@/features/history/lib/history-api";

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    statusText: ok ? "OK" : "Error",
    json: async () => body,
  } as unknown as Response;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("history-api client", () => {
  it("requests events through the history proxy with query params", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ events: [{ seq: 1 }] }));
    vi.stubGlobal("fetch", fetchMock);

    const page = await listHistoryEventPage("game 1", {
      afterSeq: 3,
      limit: 10,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/history/games/game%201/events?after_seq=3&limit=10",
      { cache: "no-store" }
    );
    expect(page.events).toEqual([{ seq: 1 }]);
    expect(page.nextAfterSeq).toBeNull();
  });

  it("accepts a bare array of snapshots", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse([{ snapshot_at_seq: 5 }]));
    vi.stubGlobal("fetch", fetchMock);

    const snapshots = await listHistorySnapshots("game-1");
    expect(snapshots).toEqual([{ snapshot_at_seq: 5 }]);
  });

  it("posts the restore body to the history proxy", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ status: "completed" }));
    vi.stubGlobal("fetch", fetchMock);

    const outcome = await restoreGame("game-1", {
      target_seq: 4,
      mode: "in_place",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/history/games/game-1/restore",
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ target_seq: 4, mode: "in_place" }),
      }
    );
    expect(outcome).toEqual({ status: "completed" });
  });

  it("lists games with recorded history", async () => {
    const games = [
      {
        game_id: "demo-eval-001",
        event_count: 8,
        first_recorded_at: "2026-06-28T00:00:00Z",
        last_recorded_at: "2026-06-28T01:00:00Z",
      },
    ];
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ games }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await listHistoryGames();

    expect(fetchMock).toHaveBeenCalledWith("/api/proxy/history/games", {
      cache: "no-store",
    });
    expect(result).toEqual(games);
  });

  it("accepts a bare array of games", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse([{ game_id: "g1", event_count: 1 }]));
    vi.stubGlobal("fetch", fetchMock);

    const result = await listHistoryGames();
    expect(result).toEqual([{ game_id: "g1", event_count: 1 }]);
  });

  it("deletes a game's history via the history proxy", async () => {
    const body = {
      game_id: "game 1",
      deleted_events: 8,
      deleted_snapshots: 1,
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(body));
    vi.stubGlobal("fetch", fetchMock);

    const result = await deleteHistoryGame("game 1");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/history/games/game%201",
      { method: "DELETE" }
    );
    expect(result).toEqual(body);
  });

  it("throws with the error detail on a non-ok response", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ detail: "not found" }, false, 404));
    vi.stubGlobal("fetch", fetchMock);

    await expect(listHistoryEventPage("game-1")).rejects.toThrow("not found");
  });
});

describe("listAllHistoryEvents", () => {
  /** Serve `total` events in pages of `pageSize`, the way the service does. */
  function pagingFetch(total: number, pageSize: number) {
    return vi.fn((url: string) => {
      const after = Number(
        new URL(url, "http://x").searchParams.get("after_seq") ?? 0
      );
      const events = [];
      for (
        let seq = after + 1;
        seq <= Math.min(after + pageSize, total);
        seq += 1
      ) {
        events.push({ seq });
      }
      const next =
        events.length === pageSize ? events[events.length - 1].seq : null;
      return Promise.resolve(jsonResponse({ events, next_after_seq: next }));
    });
  }

  it("follows the cursor across pages until the log is exhausted", async () => {
    // The endpoint's own default page is 100; a 122-event game must not stop there.
    const fetchMock = pagingFetch(122, 100);
    vi.stubGlobal("fetch", fetchMock);

    const timeline = await listAllHistoryEvents("game-1", { pageLimit: 100 });

    expect(timeline.events).toHaveLength(122);
    expect(timeline.events[121].seq).toBe(122);
    expect(timeline.truncated).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[1][0])).toContain("after_seq=100");
  });

  it("requests the server's maximum page size by default", async () => {
    const fetchMock = pagingFetch(5, 1000);
    vi.stubGlobal("fetch", fetchMock);

    await listAllHistoryEvents("game-1");

    expect(String(fetchMock.mock.calls[0][0])).toContain("limit=1000");
  });

  it("stops at a single request when the log fits in one page", async () => {
    const fetchMock = pagingFetch(40, 1000);
    vi.stubGlobal("fetch", fetchMock);

    const timeline = await listAllHistoryEvents("game-1");

    expect(timeline.events).toHaveLength(40);
    expect(timeline.truncated).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("reports truncation instead of silently stopping at the safety bound", async () => {
    const fetchMock = pagingFetch(500, 10);
    vi.stubGlobal("fetch", fetchMock);

    const timeline = await listAllHistoryEvents("game-1", {
      pageLimit: 10,
      maxEvents: 30,
    });

    expect(timeline.events).toHaveLength(30);
    expect(timeline.truncated).toBe(true);
  });
});
