import { GamePlatform, GameSession } from "@/features/shared/lib/types";
import { dragncardsRoomUrl } from "@/features/shared/lib/dragncards";

export interface ViewerUrls {
  dragncardsFrontendUrl: string;
  marvelLcgBaseUrl: string;
}

/** The only place dashboard game viewer URLs are composed. */
export function resolveGameViewerUrl(
  game: GameSession | null | undefined,
  urls: ViewerUrls,
  seat?: string | null
): string | null {
  if (!game) return null;
  const platform: GamePlatform = game.platform ?? "dragncards";
  if (platform === "dragncards") {
    return game.room_slug && urls.dragncardsFrontendUrl
      ? dragncardsRoomUrl(urls.dragncardsFrontendUrl, game.room_slug)
      : null;
  }
  if (platform === "marvel-lcg" && urls.marvelLcgBaseUrl) {
    if (!seat) return new URL("/watch", urls.marvelLcgBaseUrl).toString();
    const match = /^player([1-4])$/.exec(seat);
    if (!match) return null;
    const url = new URL("/", urls.marvelLcgBaseUrl);
    url.searchParams.set("p", String(Number(match[1]) - 1));
    return url.toString();
  }
  return null;
}

export function viewerConfigurationMessage(game: GameSession | null | undefined, urls: ViewerUrls): string {
  if (!game) return "Select a game to view";
  const platform = game.platform ?? "dragncards";
  if (platform === "dragncards" && !urls.dragncardsFrontendUrl) return "Configuration error: DRAGNCARDS_FRONTEND_URL is not set";
  if (platform === "marvel-lcg" && !urls.marvelLcgBaseUrl) return "Configuration error: MARVEL_LCG_BASE_URL is not set";
  if (platform !== "dragncards" && platform !== "marvel-lcg") return `No viewer is configured for platform “${platform}”.`;
  return platform === "dragncards" ? "This game has no room slug to open." : "This game has no supported viewer target.";
}
