import { afterEach, describe, expect, it, vi } from "vitest";

import {
  deleteHistoryGame,
  listHistoryEvents,
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

    const events = await listHistoryEvents("game 1", {
      afterSeq: 3,
      limit: 10,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/history/games/game%201/events?after_seq=3&limit=10",
      { cache: "no-store" }
    );
    expect(events).toEqual([{ seq: 1 }]);
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

    await expect(listHistoryEvents("game-1")).rejects.toThrow("not found");
  });
});
