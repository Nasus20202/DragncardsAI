"use client";

import { Alert, Button, Card, Chip, Spinner } from "@heroui/react";

import { RightDrawer } from "@/features/shared/components/right-drawer";
import {
  EvaluationQueueRequest,
  EvaluationRequestStatus,
} from "@/features/shared/lib/types";
import {
  isRequestActive,
  progressLabel,
  requestPlayers,
  requestScopeLabel,
} from "@/features/history/lib/eval-queue";

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
 * terminal, plus a header "Clear all" for every terminal request. Presentational
 * only — all polling/cancel/clear lifecycle lives in `useEvaluationQueue`.
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
          <Alert status="danger" role="alert" className="mb-3">
            {error}
          </Alert>
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
              return (
                <li key={request.request_id}>
                  <Card
                    data-testid={`history-eval-queue-item-${request.request_id}`}
                    className="flex flex-col gap-1.5 px-3 py-2 text-sm"
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
                  </Card>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </RightDrawer>
  );
}
