"use client";

import { useEffect, useState } from "react";

import { GamePlatform, HistoryEvent } from "@/features/shared/lib/types";
import { fetchHistoryEvent } from "@/features/history/lib/history-api";

export interface UseEventDetailResult {
  /** The complete event, or null until it has been fetched. */
  event: HistoryEvent | null;
  isLoading: boolean;
  error: string | null;
}

/**
 * One event's complete payload, fetched the first time it is actually needed.
 *
 * The transcript lists timeline entries, whose payloads omit the raw DragnCards
 * state and the agent conversation — the two fields that make a full listing
 * enormous. Those are exactly the fields an expanded event body shows, so the
 * body is where the full event is fetched: one ~450 KB request for the event a
 * reader opened, instead of that much for every event they did not.
 *
 * Fetching is skipped entirely while `enabled` is false, and re-fetching is
 * skipped once the event has been loaded — the log is append-only, so a recorded
 * event never changes.
 */
export function useEventDetail(
  gameId: string | null,
  seq: number,
  enabled: boolean,
  platform: GamePlatform = "dragncards"
): UseEventDetailResult {
  // One settled outcome rather than three pieces of state. "Loading" is then
  // *derived* — enabled with nothing settled yet — so entering it needs no
  // setState from inside the effect, which would cascade a render.
  const [outcome, setOutcome] = useState<
    { event: HistoryEvent } | { error: string } | null
  >(null);

  useEffect(() => {
    if (!enabled || !gameId || outcome !== null) return;
    let cancelled = false;
    fetchHistoryEvent(gameId, seq, platform)
      .then((loaded) => {
        if (cancelled) return;
        setOutcome(
          loaded
            ? { event: loaded }
            : { error: "This event is no longer recorded." }
        );
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setOutcome({
          error: e instanceof Error ? e.message : "Failed to load the event.",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, gameId, platform, seq, outcome]);

  return {
    event: outcome && "event" in outcome ? outcome.event : null,
    isLoading: enabled && Boolean(gameId) && outcome === null,
    error: outcome && "error" in outcome ? outcome.error : null,
  };
}
