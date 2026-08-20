"use client";

import { GamesSessionList } from "@/features/games/components/games-session-list";
import { DragnCardsIframe } from "@/features/games/components/dragncards-iframe";
import { useGames } from "@/features/games/lib/use-games";

export function GamesWorkspace() {
  const {
    games,
    selectedGame,
    frontendUrl,
    marvelLcgBaseUrl,
    error,
    isLoading,
    selectGame,
  } = useGames();

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <span className="text-sm text-default-500">Loading games...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-danger">
        {error}
      </div>
    );
  }

  return (
    <div className="relative flex h-full overflow-hidden">
      <aside className="flex w-64 shrink-0 flex-col border-r border-default-200/60 bg-background">
        <GamesSessionList
          games={games}
          selectedGameId={selectedGame?.id ?? null}
          onSelect={selectGame}
        />
      </aside>
      <div className="flex-1 overflow-hidden">
        <DragnCardsIframe
          game={selectedGame}
          urls={{ dragncardsFrontendUrl: frontendUrl, marvelLcgBaseUrl }}
        />
      </div>
    </div>
  );
}
