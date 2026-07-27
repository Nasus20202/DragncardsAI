"use client";

import { Button, Chip, Table } from "@heroui/react";
import { useMemo } from "react";

import { RightDrawer } from "@/features/shared/components/right-drawer";
import { HistoryEvent } from "@/features/shared/lib/types";
import {
  PlayerLevelScores,
  buildPlayerScorecard,
  formatScore,
} from "@/features/history/lib/history-rounds";

/**
 * One level's cell on the scorecard: the average overall score (with the count
 * of underlying verdicts) for a player at the move/round/game level, or a dash
 * when that player has no verdict at that level yet.
 */
function ScoreCell({ level }: { level: PlayerLevelScores }) {
  const average = formatScore(level.average);
  if (!average) {
    return <span className="text-default-300">—</span>;
  }
  return (
    <span className="flex items-center gap-1.5">
      <Chip size="sm" variant="primary" color="success">
        {average}
      </Chip>
      {level.scores.length > 1 && (
        <span className="text-xs text-default-400">
          avg of {level.scores.length}
        </span>
      )}
    </span>
  );
}

/**
 * The per-player game scorecard: each player's move/round/game overall scores
 * side by side so players can be compared. Shown in a right-side drawer opened
 * from the workspace header. Derived entirely from the evaluation events; shows
 * a needs-evaluation empty state when there are no per-player verdicts yet.
 */
export function HistoryScorecard({
  events,
  onClose,
}: {
  events: HistoryEvent[];
  onClose: () => void;
}) {
  const rows = useMemo(() => buildPlayerScorecard(events), [events]);

  return (
    <RightDrawer
      ariaLabel="Player scorecard"
      testId="history-scorecard"
      maxWidthClass="max-w-lg"
      onClose={onClose}
    >
      <div className="flex shrink-0 items-center justify-between border-b border-default-200/60 px-4 py-3">
        <div className="flex flex-col">
          <span className="text-sm font-semibold text-foreground">
            Player scorecard
          </span>
          <span className="text-xs text-default-400">
            Move, round, and game scores per player, side by side.
          </span>
        </div>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          data-testid="history-scorecard-close"
          onPress={onClose}
        >
          Close
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-auto p-4">
        {rows.length === 0 ? (
          <div
            data-testid="history-scorecard-empty"
            className="flex h-full items-center justify-center px-4 text-center text-sm text-default-500"
          >
            No per-player evaluations yet. Run a whole-game cascade from the
            Evaluate panel to score each player.
          </div>
        ) : (
          <Table aria-label="Player scorecard" className="w-full text-sm">
            <Table.Content>
              <Table.Header>
                <Table.Column isRowHeader>Player</Table.Column>
                <Table.Column>Move</Table.Column>
                <Table.Column>Round</Table.Column>
                <Table.Column>Game</Table.Column>
              </Table.Header>
              <Table.Body>
                {rows.map((row) => (
                  <Table.Row
                    key={row.player}
                    data-testid={`history-scorecard-player-${row.player}`}
                  >
                    <Table.Cell>
                      <Chip
                        size="sm"
                        variant="soft"
                        color="default"
                        className="bg-secondary/15 text-secondary"
                      >
                        {row.player}
                      </Chip>
                    </Table.Cell>
                    <Table.Cell>
                      <ScoreCell level={row.move} />
                    </Table.Cell>
                    <Table.Cell>
                      <ScoreCell level={row.round} />
                    </Table.Cell>
                    <Table.Cell>
                      <ScoreCell level={row.game} />
                    </Table.Cell>
                  </Table.Row>
                ))}
              </Table.Body>
            </Table.Content>
          </Table>
        )}
      </div>
    </RightDrawer>
  );
}
