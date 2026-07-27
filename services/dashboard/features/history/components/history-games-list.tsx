import { Button } from "@heroui/react";

import { HistoryGame } from "@/features/shared/lib/types";
import { formatActivity } from "@/features/history/lib/history-games";

function gameLabel(game: HistoryGame, names: Record<string, string>): string {
  const friendly = names[game.game_id];
  return friendly && friendly.trim() ? friendly : game.game_id;
}

/**
 * Left games-list sidebar, mirroring Play's `PlaySessionList`: one selectable
 * row per recorded game (friendly name → falls back to id, event count,
 * last-activity), collapsible, with a hover-revealed delete affordance.
 */
export function HistoryGamesList({
  games,
  gameNames,
  selectedGameId,
  isCollapsed,
  isBusy,
  onToggleCollapsed,
  onSelect,
  onRemove,
}: {
  games: HistoryGame[];
  gameNames: Record<string, string>;
  selectedGameId: string | null;
  isCollapsed: boolean;
  isBusy: boolean;
  onToggleCollapsed: () => void;
  onSelect: (gameId: string) => void;
  onRemove: (gameId: string) => void;
}) {
  return (
    <div className="flex h-full flex-col" data-testid="history-games-list">
      {/* ── Toolbar ───────────────────────────────────────────── */}
      <div className="flex h-11 shrink-0 items-center justify-between border-b border-default-200/60 px-2">
        {!isCollapsed && (
          <span className="truncate px-1 text-xs font-semibold uppercase tracking-widest text-default-400">
            Games
          </span>
        )}
        <div
          className={`flex items-center gap-1 ${isCollapsed ? "w-full justify-center" : ""}`}
        >
          <Button
            data-testid="history-games-collapse"
            aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            type="button"
            isIconOnly
            size="sm"
            variant="ghost"
            className="flex h-7 w-7 min-w-0 items-center justify-center rounded p-0 text-default-400 transition-colors hover:bg-default-100 hover:text-foreground"
            onPress={onToggleCollapsed}
          >
            <span aria-hidden="true">{isCollapsed ? "›" : "‹"}</span>
          </Button>
        </div>
      </div>

      {/* ── Games list ────────────────────────────────────────── */}
      <div className="min-h-0 flex-1 overflow-y-auto py-1">
        {games.length === 0 && !isCollapsed && (
          <p className="px-3 py-3 text-xs text-default-400">
            No recorded games yet.
          </p>
        )}

        {games.map((game) => {
          const active = game.game_id === selectedGameId;
          const label = gameLabel(game, gameNames);

          return (
            <div
              key={game.game_id}
              className={[
                "group relative flex items-center transition-colors",
                active
                  ? "bg-default-100 text-foreground"
                  : "text-default-600 hover:bg-default-100/60 hover:text-foreground",
              ].join(" ")}
            >
              <Button
                data-testid={`history-game-${game.game_id}`}
                aria-label={label}
                aria-current={active ? "true" : undefined}
                type="button"
                variant="ghost"
                className={[
                  "h-auto min-w-0 flex-1 rounded-none bg-transparent text-left",
                  isCollapsed
                    ? "flex justify-center px-2 py-3"
                    : "flex items-center gap-2.5 py-2.5 pl-3 pr-2",
                ].join(" ")}
                onPress={() => onSelect(game.game_id)}
              >
                <span
                  aria-hidden="true"
                  className="mt-0.5 h-2 w-2 shrink-0 rounded-full bg-primary/60"
                />

                {!isCollapsed && (
                  <div className="min-w-0 flex-1">
                    <div
                      className="truncate text-sm font-medium leading-tight"
                      title={label}
                    >
                      {label}
                    </div>
                    <div className="mt-0.5 truncate text-xs text-default-400">
                      {game.event_count} event
                      {game.event_count === 1 ? "" : "s"} ·{" "}
                      {formatActivity(game.last_recorded_at)}
                    </div>
                  </div>
                )}
              </Button>

              {!isCollapsed && (
                <Button
                  data-testid={`history-game-delete-${game.game_id}`}
                  aria-label={`Delete history for ${label}`}
                  type="button"
                  isIconOnly
                  size="sm"
                  variant="ghost"
                  isDisabled={isBusy}
                  className="mr-1.5 flex h-6 w-6 min-w-0 shrink-0 items-center justify-center rounded p-0 text-default-400 opacity-0 transition-opacity hover:bg-default-200/70 hover:text-danger focus-visible:opacity-100 disabled:pointer-events-none disabled:opacity-0 group-hover:opacity-100"
                  onPress={() => onRemove(game.game_id)}
                >
                  <span aria-hidden="true">✕</span>
                </Button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
