"use client";

import { Alert, Button, Spinner } from "@heroui/react";

import { DragnCardsIframe } from "@/features/games/components/dragncards-iframe";
import { Reconstruction } from "@/features/history/lib/use-board-reconstruction";

/**
 * The "open board at this event" trigger, shown in the controls column. The
 * reconstruction lifecycle lives in `useBoardReconstruction`; this is the
 * presentational button + error/help text only.
 */
export function BoardOpenControl({
  gameId,
  selectedSeq,
  isOpening,
  error,
  isOpen,
  onOpen,
}: {
  gameId: string | null;
  selectedSeq: number | null;
  isOpening: boolean;
  error: string | null;
  isOpen: boolean;
  onOpen: () => void;
}) {
  return (
    <div
      className="flex flex-col gap-2 border-t border-default-200/60 p-4"
      data-testid="board-control"
    >
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-foreground">Board</span>
        <span className="text-xs text-default-400">
          Reconstruct and click around the board at the selected moment.
        </span>
      </div>
      <Button
        type="button"
        variant="secondary"
        isDisabled={gameId === null || selectedSeq === null || isOpening}
        data-testid="board-open"
        onPress={onOpen}
      >
        {isOpening ? (
          <Spinner size="sm" />
        ) : isOpen ? (
          "Reopen board at this event"
        ) : (
          "Open board at this event"
        )}
      </Button>
      {selectedSeq === null && (
        <span className="text-xs text-default-400">
          Select a timeline event first.
        </span>
      )}
      {error && (
        <Alert status="danger" role="alert" data-testid="board-error">
          {error}
        </Alert>
      )}
    </div>
  );
}

/**
 * The embedded reconstructed board for the selected moment, shown in the main
 * panel while a reconstruction is live.
 */
export function BoardView({
  reconstruction,
  frontendUrl,
  onClose,
}: {
  reconstruction: Reconstruction;
  frontendUrl: string;
  onClose: () => void;
}) {
  return (
    <div
      className="flex h-full min-h-0 flex-col"
      data-testid="board-reconstruction"
    >
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-default-200/60 px-4 py-2">
        <span className="text-sm font-semibold text-foreground">
          Board at event #{reconstruction.seq}
        </span>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          data-testid="board-close"
          onPress={onClose}
        >
          Close board
        </Button>
      </div>
      <div className="min-h-0 flex-1">
        <DragnCardsIframe
          roomSlug={reconstruction.roomSlug}
          frontendUrl={frontendUrl}
        />
      </div>
    </div>
  );
}
