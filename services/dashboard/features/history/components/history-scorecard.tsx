"use client";

import { Alert, Button, Chip } from "@heroui/react";
import { useMemo } from "react";

import { ScoreChip } from "@/features/history/components/score-chip";
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
 * when that player has no verdict at that level yet. The chip's colour comes
 * from the average itself, so a weak player's row reads red and a strong one's
 * green without the numbers being compared.
 */
function ScoreCell({ level }: { level: PlayerLevelScores }) {
  const average = formatScore(level.average);
  if (!average) {
    return <span className="text-default-300">—</span>;
  }
  return (
    <span className="flex items-center gap-1.5">
      <ScoreChip value={level.average} />
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
  const { rows, evaluatorVersion, excludedCount } = useMemo(
    () => buildPlayerScorecard(events),
    [events]
  );

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
            {evaluatorVersion ? ` Graded by ${evaluatorVersion}.` : ""}
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
          <>
            {excludedCount > 0 && (
              <Alert
                status="warning"
                className="mb-3"
                data-testid="history-scorecard-version-notice"
              >
                <Alert.Content>
                  <Alert.Description>
                    {excludedCount} verdict{excludedCount === 1 ? "" : "s"} from
                    an earlier evaluator version{" "}
                    {excludedCount === 1 ? "is" : "are"} not averaged here.
                    Scores only compare within one version, because a change to
                    what the judge is shown or asked moves the scale.
                    Re-evaluate those targets to bring them onto this scale.
                  </Alert.Description>
                </Alert.Content>
              </Alert>
            )}
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-left text-xs font-semibold uppercase tracking-wide text-default-400">
                  <th className="py-2 pr-3">Player</th>
                  <th className="py-2 pr-3">Move</th>
                  <th className="py-2 pr-3">Round</th>
                  <th className="py-2">Game</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.player}
                    data-testid={`history-scorecard-player-${row.player}`}
                    className="border-t border-default-200/60"
                  >
                    <td className="py-2 pr-3">
                      <Chip
                        size="sm"
                        variant="soft"
                        color="default"
                        className="bg-secondary/15 text-secondary"
                      >
                        {row.player}
                      </Chip>
                    </td>
                    <td className="py-2 pr-3">
                      <ScoreCell level={row.move} />
                    </td>
                    <td className="py-2 pr-3">
                      <ScoreCell level={row.round} />
                    </td>
                    <td className="py-2">
                      <ScoreCell level={row.game} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </RightDrawer>
  );
}
