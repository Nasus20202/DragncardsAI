import { useCallback, useEffect, useRef } from "react";

/** The context indicator cadence while a generation is in progress. */
export const CONTEXT_METADATA_POLL_INTERVAL_MS = 5000;

interface UseContextMetadataPollingOptions {
  sessionId: string | null;
  isActive: boolean;
  refreshContextMetadata: (sessionId: string) => Promise<void>;
}

/**
 * Refresh context metadata immediately and periodically while a generation runs.
 *
 * The next timeout is scheduled after a refresh settles rather than on a fixed
 * interval. This keeps a slow context request from overlapping the next poll.
 * The caller owns loading/error state; this hook only coordinates refresh timing.
 */
export function useContextMetadataPolling({
  sessionId,
  isActive,
  refreshContextMetadata,
}: UseContextMetadataPollingOptions): void {
  const refreshContextMetadataRef = useRef(refreshContextMetadata);
  useEffect(() => {
    refreshContextMetadataRef.current = refreshContextMetadata;
  }, [refreshContextMetadata]);

  const inFlightRefreshesRef = useRef(new Map<string, Promise<void>>());
  const refreshOnce = useCallback((currentSessionId: string): Promise<void> => {
    const inFlight = inFlightRefreshesRef.current.get(currentSessionId);
    if (inFlight) {
      return inFlight;
    }

    const refresh: Promise<void> = refreshContextMetadataRef
      .current(currentSessionId)
      .finally(() => {
        if (inFlightRefreshesRef.current.get(currentSessionId) === refresh) {
          inFlightRefreshesRef.current.delete(currentSessionId);
        }
      });
    inFlightRefreshesRef.current.set(currentSessionId, refresh);
    return refresh;
  }, []);

  useEffect(() => {
    if (!sessionId || !isActive) {
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const scheduleNext = () => {
      if (!cancelled) {
        timer = setTimeout(tick, CONTEXT_METADATA_POLL_INTERVAL_MS);
      }
    };

    const tick = () => {
      if (cancelled) {
        return;
      }
      // The refresh callback currently handles failures as non-fatal. Handling
      // rejection here as well keeps this timer loop safe if that callback is
      // replaced by a caller with a rejecting implementation.
      void refreshOnce(sessionId).then(scheduleNext, scheduleNext);
    };

    tick();

    return () => {
      cancelled = true;
      if (timer !== null) {
        clearTimeout(timer);
      }
    };
  }, [isActive, refreshOnce, sessionId]);
}
