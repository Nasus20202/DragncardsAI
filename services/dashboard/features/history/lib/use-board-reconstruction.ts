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
  /** The game it was built from, so a stale board is never shown for another. */
  gameId: string;
}

/**
 * A failed open, tagged with what was selected at the time, so the message is
 * shown against that selection only and does not linger over another moment.
 */
interface OpenFailure {
  gameId: string | null;
  seq: number | null;
  message: string;
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
 *
 * Moving the selection within the same game RETAINS the session rather than
 * disposing it, so re-opening re-points the room it already owns instead of
 * building a second one (measured: ~55 ms against ~730 ms). What is dropped is the
 * rendered board, not the session — a board left on screen while the selection
 * moved would sit under a header naming a different moment. Everything that
 * genuinely ends the view — explicit close, a different game, unmount, page
 * unload — still disposes the session.
 */
export function useBoardReconstruction(
  gameId: string | null,
  selectedSeq: number | null,
  platform: "dragncards" | "marvel-lcg" = "dragncards"
): BoardReconstruction {
  const [built, setBuilt] = useState<Reconstruction | null>(null);
  const [isOpening, setIsOpening] = useState(false);
  const [failure, setFailure] = useState<OpenFailure | null>(null);

  // What is on screen is DERIVED from the selection rather than cleared by an
  // effect. A board is shown only while the selection still matches what it was
  // built from: its header names that moment, so showing it under a different
  // selection would make the label lie. Deriving it means there is one source of
  // truth for that fact and no render where the two disagree — an effect that
  // cleared it would necessarily paint the mismatch once first.
  const reconstruction =
    built && built.gameId === gameId && built.seq === selectedSeq
      ? built
      : null;
  const error =
    failure && failure.gameId === gameId && failure.seq === selectedSeq
      ? failure.message
      : null;

  // Mirror the live session id so unload handlers and unmount cleanup always
  // observe the current value without re-binding.
  const activeSessionRef = useRef<string | null>(null);
  // The room the active session owns, remembered so a reuse restore — which
  // creates no room and therefore reports none — does not have to rediscover it
  // by listing every live session.
  const activeRoomSlugRef = useRef<string | null>(null);

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
    activeRoomSlugRef.current = null;
    setBuilt(null);
    setFailure(null);
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
        activeRoomSlugRef.current = null;
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
        activeRoomSlugRef.current = null;
        void disposeSession(sessionId);
      }
    };
  }, [disposeSession]);

  // Only one reconstruction is live at a time, and we never auto-open the next
  // one. What changed with reuse is what "moving on" costs:
  //
  // - A different MOMENT of the same game keeps the session, so re-opening
  //   re-points the room it already owns instead of building a second one. Nothing
  //   happens here for that case: the board stops being rendered because it is
  //   derived from the selection, not because an effect cleared it.
  // - A different GAME disposes the session, including when nothing is on screen.
  //   A session built for one game holds that game's plugin and cannot be
  //   re-pointed at another, so there is nothing to keep — and a retained session
  //   survives the board being hidden, which makes this the only thing that
  //   reclaims it.
  const reconGameRef = useRef<string | null>(gameId);
  useEffect(() => {
    const gameChanged = reconGameRef.current !== gameId;
    reconGameRef.current = gameId;
    if (gameChanged && activeSessionRef.current) close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gameId]);

  const open = useCallback(async () => {
    if (!gameId || selectedSeq === null) return;
    if (platform !== "dragncards") {
      setFailure({ gameId, seq: selectedSeq, message: "This platform cannot be rewound into a throwaway copy." });
      return;
    }
    setFailure(null);
    setIsOpening(true);

    // A session retained from a previous moment of this game is offered back for
    // reuse rather than disposed. The history-service re-points it when it can,
    // and creates a fresh session when it cannot — so the session id is read back
    // off the response below rather than assumed.
    const retained = activeSessionRef.current;
    const retainedRoomSlug = activeRoomSlugRef.current;

    try {
      const outcome = await restoreGame(gameId, {
        target_seq: selectedSeq,
        mode: "new",
        ephemeral: true,
        ...(retained ? { reuse_session_id: retained } : {}),
      });
      const sessionId = extractSessionId(outcome);
      if (!sessionId) {
        throw new Error("Restore did not return a session id.");
      }

      // The restore response names the room it created. A reuse creates none, so
      // it reports none, and the room is the one already recorded for that
      // session. Listing sessions is the last resort, kept only for a
      // history-service old enough to report no room at all: it is an extra
      // browser→proxy→service round trip after the restore already finished,
      // O(all sessions) work to answer a by-id question, and a race — a session
      // reaped in between yields no match and the board silently renders its
      // fallback.
      let roomSlug: string | null =
        typeof outcome.room_slug === "string" && outcome.room_slug
          ? outcome.room_slug
          : null;
      if (roomSlug === null && sessionId === retained) {
        roomSlug = retainedRoomSlug;
      }
      if (roomSlug === null) {
        try {
          const games = await listGames();
          roomSlug = games.find((g) => g.id === sessionId)?.room_slug ?? null;
        } catch {
          /* room resolution is best-effort; the iframe shows a fallback */
        }
      }

      // Only one reconstruction is live at a time: if the restore built a new
      // session instead of reusing the retained one, the retained one is now
      // orphaned and goes.
      if (retained && retained !== sessionId) {
        void disposeSession(retained);
      }
      activeSessionRef.current = sessionId;
      activeRoomSlugRef.current = roomSlug;

      setBuilt({ sessionId, roomSlug, seq: selectedSeq, gameId });
    } catch (e) {
      // A failed restore leaves the retained session as it was: the
      // history-service does not delete a session it did not create, so it is
      // still ours to hold and reuse on the next attempt.
      setFailure({
        gameId,
        seq: selectedSeq,
        message:
          e instanceof Error
            ? e.message
            : "Failed to open the board at this event.",
      });
    } finally {
      setIsOpening(false);
    }
  }, [gameId, selectedSeq, disposeSession, platform]);

  return { reconstruction, isOpening, error, open, close };
}
