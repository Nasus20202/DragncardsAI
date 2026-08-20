"use client";

import { GameSession } from "@/features/shared/lib/types";

interface GamesSessionListProps {
  games: GameSession[];
  selectedGameId: string | null;
  onSelect: (id: string) => void;
}

export function GamesSessionList({
  games,
  selectedGameId,
  onSelect,
}: GamesSessionListProps) {
  if (games.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-4 text-sm text-default-500">
        No active games
      </div>
    );
  }

  const sortedGames = [...games].sort(
    (a, b) =>
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  return (
    <div className="min-h-0 flex-1 overflow-y-auto py-1">
      {sortedGames.map((game) => {
        const active = game.id === selectedGameId;
        return (
          <button
            key={game.id}
            data-testid={`game-session-${game.id}`}
            type="button"
            className={[
              "w-full text-left transition-colors px-3 py-2.5",
              active
                ? "bg-default-300 text-foreground font-medium"
                : "text-default-600 hover:bg-default-100/60 hover:text-foreground",
            ].join(" ")}
            onClick={() => onSelect(game.id)}
          >
            <div className="flex flex-col items-start">
              <span className="font-bold text-sm">
                {game.platform === "marvel-lcg"
                  ? (game.game_id ?? game.id)
                  : (game.room_slug ?? game.id)}
              </span>
              <span className="text-xs text-default-500">
                {game.platform === "marvel-lcg" ? "Marvel LCG" : game.plugin}
              </span>
              <span className="text-[10px] uppercase tracking-wide text-default-400">
                {game.platform === "marvel-lcg" ? "marvel-lcg" : "dragncards"}
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
