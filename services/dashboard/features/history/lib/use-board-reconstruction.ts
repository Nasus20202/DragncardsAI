"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { listGames } from "@/features/play/lib/client-api";
import {
  deleteGameSession,
  disposeReconstructionViaBeacon,
  restoreGame,
} from "@/features/history/lib/history-api";
import { RestoreOutcome } from "@/features/shared/lib/types";

/** The currently-mounted ephemeral reconstruction. */
export interface Reconstruction {
  sessionId: string;
  roomSlug: string | null;
  /** The seq this reconstruction was built from, for the header label. */
  seq: number;
}

/**
 * `RestoreOutcome` carries the new session id under one of a couple of keys;
 * accept either.
 */
function extractSessionId(outcome: RestoreOutcome): string | null {
  if (typeof outcome.session_id === "string" && outcome.session_id) {
    return outcome.session_id;
  }
  const alt = outcome.game_session_id;
  if (typeof alt === "string" && alt) return alt;
  return null;
}

export interface BoardReconstruction {
  reconstruction: Reconstruction | null;
  isOpening: boolean;
  error: string | null;
  /** Restore the selected seq into a fresh ephemeral session and embed it. */
  open: () => Promise<void>;
  /** Dispose the live reconstruction (in-app close). */
  close: () => void;
}

/**
 * Owns the lifecycle of the on-demand "board at this event" reconstruction:
 * restore (ephemeral) → resolve room_slug → embed; with single-live-at-a-time
 * semantics and teardown on unmount, deselect/switch, and tab close.
 *
 * Teardown deletes the game-service session ONLY (the ephemeral session is
 * non-emitting). It is the FAST PATH — correctness rests on a server-side TTL
 * reaper, so client teardown is best-effort.
 */
export function useBoardReconstruction(
  gameId: string | null,
  selectedSeq: number | null
): BoardReconstruction {
  const [reconstruction, setReconstruction] = useState<Reconstruction | null>(
    null
  );
  const [isOpening, setIsOpening] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Mirror the live session id so unload handlers and unmount cleanup always
  // observe the current value without re-binding.
  const activeSessionRef = useRef<string | null>(null);

  const disposeSession = useCallback(async (sessionId: string) => {
    try {
      await deleteGameSession(sessionId);
    } catch {
      /* best-effort; the TTL reaper handles lost connections */
    }
  }, []);

  const close = useCallback(() => {
    const sessionId = activeSessionRef.current;
    activeSessionRef.current = null;
    setReconstruction(null);
    setError(null);
    if (sessionId) void disposeSession(sessionId);
  }, [disposeSession]);

  // Tab close / refresh / navigation: dispose via unload-safe transport.
  //
  // `pagehide` only — NOT `visibilitychange`. A hidden tab is not the end of the
  // view: switching browser tabs, minimizing, or backgrounding the app would
  // otherwise delete the session out from under a board the user is still
  // looking at, leaving the embedded room orphaned and the UI claiming a
  // reconstruction that no longer exists. `pagehide` covers unload, refresh, and
  // navigation (including the back/forward cache), and the server-side TTL
  // reaper is the safety net for anything it misses.
  useEffect(() => {
    const handleUnload = () => {
      const sessionId = activeSessionRef.current;
      if (sessionId) {
        disposeReconstructionViaBeacon(sessionId);
        activeSessionRef.current = null;
      }
    };
    window.addEventListener("pagehide", handleUnload);
    return () => {
      window.removeEventListener("pagehide", handleUnload);
    };
  }, []);

  // React unmount: dispose whatever is live.
  useEffect(() => {
    return () => {
      const sessionId = activeSessionRef.current;
      if (sessionId) {
        activeSessionRef.current = null;
        void disposeSession(sessionId);
      }
    };
  }, [disposeSession]);

  // Deselecting, switching moment, or switching game disposes the open
  // reconstruction (only one live at a time). We don't auto-open the next one.
  const reconSeq = reconstruction?.seq ?? null;
  const reconGameRef = useRef<string | null>(gameId);
  useEffect(() => {
    if (!reconstruction) {
      reconGameRef.current = gameId;
      return;
    }
    const gameChanged = reconGameRef.current !== gameId;
    const seqChanged = selectedSeq !== reconSeq;
    if (gameChanged || seqChanged) {
      reconGameRef.current = gameId;
      close();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gameId, selectedSeq, reconSeq]);

  const open = useCallback(async () => {
    if (!gameId || selectedSeq === null) return;
    setError(null);
    setIsOpening(true);

    // Only one reconstruction at a time: dispose the previous before opening.
    const previous = activeSessionRef.current;
    activeSessionRef.current = null;
    setReconstruction(null);
    if (previous) void disposeSession(previous);

    try {
      const outcome = await restoreGame(gameId, {
        target_seq: selectedSeq,
        mode: "new",
        ephemeral: true,
      });
      const sessionId = extractSessionId(outcome);
      if (!sessionId) {
        throw new Error("Restore did not return a session id.");
      }
      activeSessionRef.current = sessionId;

      // The restore response names the room it just created, so the common path
      // needs no second call. Falling back to the session list keeps an older
      // history-service (whose response carries no `room_slug`) working, but it
      // is the slow path in every sense: an extra browser→proxy→service round
      // trip after the restore already finished, O(all sessions) work to answer a
      // by-id question, and a race — if the session is reaped in between, `find`
      // returns undefined and the board silently renders its fallback.
      let roomSlug: string | null =
        typeof outcome.room_slug === "string" && outcome.room_slug
          ? outcome.room_slug
          : null;
      if (roomSlug === null) {
        try {
          const games = await listGames();
          roomSlug = games.find((g) => g.id === sessionId)?.room_slug ?? null;
        } catch {
          /* room resolution is best-effort; the iframe shows a fallback */
        }
      }

      setReconstruction({ sessionId, roomSlug, seq: selectedSeq });
    } catch (e) {
      const orphan = activeSessionRef.current;
      activeSessionRef.current = null;
      if (orphan) void disposeSession(orphan);
      setError(
        e instanceof Error
          ? e.message
          : "Failed to open the board at this event."
      );
    } finally {
      setIsOpening(false);
    }
  }, [gameId, selectedSeq, disposeSession]);

  return { reconstruction, isOpening, error, open, close };
}
