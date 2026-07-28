import { afterEach, describe, expect, it, vi } from "vitest";

import {
  deleteHistoryGame,
  fetchHistoryEvent,
  listAllHistoryTimeline,
  listHistoryEventPage,
  listHistoryGames,
  listHistorySnapshots,
  listHistoryTimelinePage,
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

describe("listHistoryTimelinePage", () => {
  it("reads the timeline resource, not the events resource", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ events: [{ seq: 1, payload_complete: false }] })
      );
    vi.stubGlobal("fetch", fetchMock);

    const page = await listHistoryTimelinePage("game 1", {
      afterSeq: 3,
      limit: 500,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/history/games/game%201/timeline?after_seq=3&limit=500",
      { cache: "no-store" }
    );
    expect(page.events).toEqual([{ seq: 1, payload_complete: false }]);
    expect(page.nextAfterSeq).toBeNull();
  });
});

describe("fetchHistoryEvent", () => {
  it("addresses one seq through the exclusive cursor", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ events: [{ seq: 7 }] }));
    vi.stubGlobal("fetch", fetchMock);

    const event = await fetchHistoryEvent("game-1", 7);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/history/games/game-1/events?after_seq=6&limit=1",
      { cache: "no-store" }
    );
    expect(event).toEqual({ seq: 7 });
  });

  it("asks from zero for the very first event", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ events: [{ seq: 1 }] }));
    vi.stubGlobal("fetch", fetchMock);

    await fetchHistoryEvent("game-1", 1);

    expect(String(fetchMock.mock.calls[0][0])).toContain("after_seq=0");
  });

  it("resolves null when the seq is not recorded", async () => {
    // The cursor is exclusive, so an absent seq yields the *next* event; that is
    // not the one asked for and must not be mistaken for it.
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ events: [{ seq: 9 }] }));
    vi.stubGlobal("fetch", fetchMock);

    expect(await fetchHistoryEvent("game-1", 7)).toBeNull();
  });

  it("resolves null on an empty page", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ events: [] }))
    );
    expect(await fetchHistoryEvent("game-1", 7)).toBeNull();
  });
});

describe("listAllHistoryTimeline", () => {
  /** Serve `total` entries in pages of `pageSize`, the way the service does. */
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
    // A 122-event game must not stop at a page boundary.
    const fetchMock = pagingFetch(122, 100);
    vi.stubGlobal("fetch", fetchMock);

    const timeline = await listAllHistoryTimeline("game-1", { pageLimit: 100 });

    expect(timeline.events).toHaveLength(122);
    expect(timeline.events[121].seq).toBe(122);
    expect(timeline.truncated).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[1][0])).toContain("after_seq=100");
  });

  it("requests the timeline endpoint's maximum page size by default", async () => {
    const fetchMock = pagingFetch(5, 5000);
    vi.stubGlobal("fetch", fetchMock);

    await listAllHistoryTimeline("game-1");

    expect(String(fetchMock.mock.calls[0][0])).toContain("/timeline?");
    expect(String(fetchMock.mock.calls[0][0])).toContain("limit=5000");
  });

  it("stops at a single request when the log fits in one page", async () => {
    const fetchMock = pagingFetch(40, 5000);
    vi.stubGlobal("fetch", fetchMock);

    const timeline = await listAllHistoryTimeline("game-1");

    expect(timeline.events).toHaveLength(40);
    expect(timeline.truncated).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("reports truncation instead of silently stopping at the safety bound", async () => {
    const fetchMock = pagingFetch(500, 10);
    vi.stubGlobal("fetch", fetchMock);

    const timeline = await listAllHistoryTimeline("game-1", {
      pageLimit: 10,
      maxEvents: 30,
    });

    expect(timeline.events).toHaveLength(30);
    expect(timeline.truncated).toBe(true);
  });

  it("resumes from a cursor so a refresh only reads what is new", async () => {
    const fetchMock = pagingFetch(120, 100);
    vi.stubGlobal("fetch", fetchMock);

    const timeline = await listAllHistoryTimeline("game-1", {
      pageLimit: 100,
      afterSeq: 100,
    });

    expect(timeline.events.map((e) => e.seq)).toEqual(
      Array.from({ length: 20 }, (_, i) => 101 + i)
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toContain("after_seq=100");
  });
});
