"use client";

import { Button, Chip, Spinner } from "@heroui/react";

import { RightDrawer } from "@/features/shared/components/right-drawer";
import {
  EvaluationQueueRequest,
  EvaluationRequestStatus,
} from "@/features/shared/lib/types";
import {
  isRequestActive,
  progressLabel,
  requestErrors,
  requestPlayers,
  requestScopeLabel,
} from "@/features/history/lib/eval-queue";

/** How many per-target failures a row lists before summarizing the rest. */
const MAX_SHOWN_ERRORS = 3;

/** Whether any listed request is terminal (clearable). */
function hasTerminalRequest(requests: EvaluationQueueRequest[]): boolean {
  return requests.some((request) => !isRequestActive(request));
}

function requestStatusColor(
  status: EvaluationRequestStatus
): "success" | "danger" | "warning" | "default" | "accent" {
  switch (status) {
    case "completed":
      return "success";
    case "failed":
      return "danger";
    case "partial":
      return "warning";
    case "running":
      return "accent";
    default:
      return "default";
  }
}

function gameLabel(gameId: string, gameNames: Record<string, string>): string {
  return gameNames[gameId] ?? gameId;
}

/**
 * The persistent, cross-game evaluations queue. Lists in-progress and recent
 * requests (newest first) with their game, scope label, status, and progress,
 * and offers a per-request Cancel while non-terminal or a per-request Clear once
 * terminal, plus a header "Clear all" for every terminal request.
 *
 * A row also lists the per-target failures the request has hit, including ones
 * recorded while it is still running, so an evaluation error is visible as it
 * happens rather than only as a final status. Presentational only — all
 * polling/cancel/clear lifecycle lives in `useEvaluationQueue`.
 */
export function EvaluationQueue({
  requests,
  gameNames,
  isLoading,
  error,
  onCancel,
  onClear,
  onClearAll,
  onClose,
}: {
  requests: EvaluationQueueRequest[];
  gameNames: Record<string, string>;
  isLoading: boolean;
  error: string | null;
  onCancel: (gameId: string, requestId: string) => void;
  onClear: (requestId: string) => void;
  onClearAll: () => void;
  onClose: () => void;
}) {
  const canClearAll = hasTerminalRequest(requests);
  return (
    <RightDrawer
      ariaLabel="Evaluations queue"
      testId="history-eval-queue"
      onClose={onClose}
    >
      <div className="flex shrink-0 items-center justify-between border-b border-default-200/60 px-4 py-3">
        <div className="flex flex-col">
          <span className="flex items-center gap-2 text-sm font-semibold text-foreground">
            Evaluations queue
            {isLoading && <Spinner size="sm" />}
          </span>
          <span className="text-xs text-default-400">
            In-progress and recent evaluations across all games.
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            data-testid="history-eval-queue-clear-all"
            isDisabled={!canClearAll}
            onPress={onClearAll}
          >
            Clear all
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            data-testid="history-eval-queue-close"
            onPress={onClose}
          >
            Close
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden p-4">
        {error && (
          <div
            role="alert"
            className="mb-3 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger"
          >
            {error}
          </div>
        )}

        {requests.length === 0 ? (
          <div
            data-testid="history-eval-queue-empty"
            className="flex h-full items-center justify-center px-4 text-center text-sm text-default-500"
          >
            No evaluations yet. Submit one from the Evaluate panel.
          </div>
        ) : (
          <ul className="flex flex-col gap-2">
            {requests.map((request) => {
              const active = isRequestActive(request);
              const players = requestPlayers(request);
              const errors = requestErrors(request);
              return (
                <li
                  key={request.request_id}
                  data-testid={`history-eval-queue-item-${request.request_id}`}
                  className="flex flex-col gap-1.5 rounded-lg border border-default-200/60 bg-default-50/40 px-3 py-2 text-sm dark:bg-white/3"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className="truncate font-medium text-foreground"
                      title={gameLabel(request.game_id, gameNames)}
                    >
                      {gameLabel(request.game_id, gameNames)}
                    </span>
                    <Chip
                      size="sm"
                      variant="soft"
                      color={requestStatusColor(request.status)}
                      data-testid={`history-eval-queue-status-${request.request_id}`}
                    >
                      {request.status}
                    </Chip>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className="text-default-600"
                      data-testid={`history-eval-queue-scope-${request.request_id}`}
                    >
                      {requestScopeLabel(request)}
                    </span>
                    <span className="text-xs text-default-400">
                      {progressLabel(request)}
                    </span>
                  </div>
                  {players.length > 0 && (
                    <div
                      className="flex flex-wrap gap-1"
                      data-testid={`history-eval-queue-players-${request.request_id}`}
                    >
                      {players.map((player) => (
                        <Chip
                          key={player}
                          size="sm"
                          variant="soft"
                          color="default"
                          className="bg-secondary/15 text-secondary"
                        >
                          {player}
                        </Chip>
                      ))}
                    </div>
                  )}
                  {errors.length > 0 && (
                    <div
                      role="alert"
                      data-testid={`history-eval-queue-errors-${request.request_id}`}
                      className="flex flex-col gap-1 rounded-lg border border-danger/30 bg-danger/10 px-2 py-1.5 text-xs text-danger"
                    >
                      {errors.slice(0, MAX_SHOWN_ERRORS).map((entry) => (
                        <span
                          key={`${entry.label}-${entry.detail}`}
                          className="break-words"
                        >
                          <span className="font-medium">{entry.label}:</span>{" "}
                          {entry.detail}
                        </span>
                      ))}
                      {errors.length > MAX_SHOWN_ERRORS && (
                        <span>+{errors.length - MAX_SHOWN_ERRORS} more</span>
                      )}
                    </div>
                  )}
                  <div className="flex justify-end">
                    {active ? (
                      <Button
                        type="button"
                        size="sm"
                        variant="danger-soft"
                        data-testid={`history-eval-queue-cancel-${request.request_id}`}
                        onPress={() =>
                          onCancel(request.game_id, request.request_id)
                        }
                      >
                        Cancel
                      </Button>
                    ) : (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        data-testid={`history-eval-queue-clear-${request.request_id}`}
                        onPress={() => onClear(request.request_id)}
                      >
                        Clear
                      </Button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </RightDrawer>
  );
}
