"use client";

import { Button, Chip, Spinner } from "@heroui/react";

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
        <span className="text-sm font-semibold text-foreground">
          Look at it
        </span>
        <Chip size="sm" variant="soft" color="success">
          Read-only
        </Chip>
      </div>
      <p className="text-xs text-default-400">
        Opens a throwaway copy of the board as it was at this moment, to click
        around in. This game is not changed, and the copy is discarded when you
        close it.
      </p>
      <Button
        type="button"
        variant="secondary"
        isDisabled={gameId === null || selectedSeq === null || isOpening}
        data-testid="board-open"
        onPress={onOpen}
      >
        {isOpening ? (
          <span className="flex items-center gap-2">
            <Spinner size="sm" />
            <span>Building the board…</span>
          </span>
        ) : isOpen ? (
          "Reopen board at this event"
        ) : (
          "Open board at this event"
        )}
      </Button>
      {isOpening && (
        <span className="text-xs text-default-400" data-testid="board-opening">
          Creating a temporary DragnCards room and loading the recorded state
          into it. This takes a few seconds.
        </span>
      )}
      {selectedSeq === null && (
        <span className="text-xs text-default-400">
          Select a timeline event first.
        </span>
      )}
      {error && (
        <div
          role="alert"
          data-testid="board-error"
          className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger"
        >
          {error}
        </div>
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
      <div className="flex shrink-0 flex-col gap-1 border-b border-default-200/60 px-4 py-2">
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-2">
            <span className="text-sm font-semibold text-foreground">
              Board at event #{reconstruction.seq}
            </span>
            <Chip size="sm" variant="soft" color="success">
              Temporary copy
            </Chip>
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
        {/*
          The single most-asked question about this view: whether poking at this
          board is touching the real game. It is not — the reconstruction is a
          separate ephemeral session — so the view says so plainly rather than
          leaving the user to infer it from an unfamiliar room appearing where
          their transcript used to be.
        */}
        <span
          className="text-xs text-default-400"
          data-testid="board-scratch-notice"
        >
          A throwaway copy for looking around. Nothing you do here affects the
          recorded game, and it is discarded when you close this.
        </span>
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
