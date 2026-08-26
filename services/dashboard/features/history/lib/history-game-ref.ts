import { GamePlatform, HistoryGame } from "@/features/shared/lib/types";

/** The platform-qualified identity of one history-service game partition. */
export interface HistoryGameRef {
  gameId: string;
  platform: GamePlatform;
}

export function historyGameRef(game: HistoryGame): HistoryGameRef {
  return { gameId: game.game_id, platform: game.platform ?? "dragncards" };
}

export function sameHistoryGameRef(
  left: HistoryGameRef | null,
  right: HistoryGameRef | null
): boolean {
  return (
    left !== null &&
    right !== null &&
    left.gameId === right.gameId &&
    left.platform === right.platform
  );
}

export function historyGameRefKey(ref: HistoryGameRef | null): string | null {
  return ref ? `${ref.platform}:${ref.gameId}` : null;
}

/** Keep legacy DragnCards automation selectors stable while qualifying Marvel. */
export function historyGameTestId(ref: HistoryGameRef): string {
  return ref.platform === "dragncards"
    ? `history-game-${ref.gameId}`
    : `history-game-${ref.platform}-${ref.gameId}`;
}

export function historyGameDeleteTestId(ref: HistoryGameRef): string {
  return ref.platform === "dragncards"
    ? `history-game-delete-${ref.gameId}`
    : `${historyGameTestId(ref)}-delete`;
}

export function findHistoryGame(
  games: HistoryGame[],
  ref: HistoryGameRef | null
): HistoryGame | null {
  if (!ref) return null;
  return (
    games.find((game) => sameHistoryGameRef(historyGameRef(game), ref)) ?? null
  );
}

/** Resolve a URL/import game id while retaining DragnCards compatibility. */
export function resolveHistoryGameRef(
  games: HistoryGame[],
  gameId: string,
  platform?: GamePlatform | null
): HistoryGameRef | null {
  const matches = games.filter((game) => game.game_id === gameId);
  const resolved =
    matches.find((game) => (game.platform ?? "dragncards") === platform) ??
    (platform == null
      ? matches.find((game) => (game.platform ?? "dragncards") === "dragncards")
      : undefined) ??
    matches[0];
  return resolved ? historyGameRef(resolved) : null;
}
