import { describe, expect, it } from "vitest";

import { resolveGameViewerUrl } from "@/features/games/lib/viewer-resolver";

const urls = {
  dragncardsFrontendUrl: "http://dragncards.test",
  marvelLcgBaseUrl: "http://marvel.test:4006",
};

const game = (platform: "dragncards" | "marvel-lcg") => ({
  id: "game-1",
  plugin: "marvel-champions",
  plugin_id: 1,
  created_at: "2026-01-01",
  room_slug: platform === "dragncards" ? "room-1" : null,
  platform,
});

describe("resolveGameViewerUrl", () => {
  it("keeps DragnCards on its room template", () => {
    expect(resolveGameViewerUrl(game("dragncards"), urls)).toBe(
      "http://dragncards.test/room/room-1"
    );
  });

  it("opens Marvel LCG read-only by default", () => {
    const value = resolveGameViewerUrl(game("marvel-lcg"), urls);
    expect(value).toBe("http://marvel.test:4006/watch");
    expect(value).not.toMatch(/debug|show|replay/i);
  });

  it("maps neutral seats only at the viewer edge", () => {
    expect(resolveGameViewerUrl(game("marvel-lcg"), urls, "player2")).toBe(
      "http://marvel.test:4006/?p=1"
    );
  });
});
