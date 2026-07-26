"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { EvaluationQueueRequest } from "@/features/shared/lib/types";
import {
  cancelEvaluation,
  clearEvaluations,
  deleteEvaluation,
  listEvaluations,
} from "@/features/history/lib/eval-api";
import {
  countActiveRequests,
  countTerminalRequests,
} from "@/features/history/lib/eval-queue";

const POLL_INTERVAL_MS = 2000;
const QUEUE_LIMIT = 50;

export interface EvaluationQueue {
  requests: EvaluationQueueRequest[];
  /** Number of requests with at least one non-terminal target. */
  activeCount: number;
  /** Number of fully-terminal (clearable) requests. */
  terminalCount: number;
  isLoading: boolean;
  error: string | null;
  /** Re-fetch the listing now (e.g. right after a submit). */
  refresh: () => void;
  /** Cancel a request, then refresh the listing. */
  cancel: (gameId: string, requestId: string) => Promise<void>;
  /** Clear a single terminal request, then refresh the listing. */
  remove: (requestId: string) => Promise<void>;
  /** Clear all terminal requests, then refresh the listing. */
  clearTerminal: () => Promise<void>;
}

/**
 * Polls the cross-game evaluations listing to drive the persistent queue.
 *
 * Polling runs while the queue panel is `open` OR any request is still active,
 * and stops once the panel is closed and nothing is in flight (so we never keep
 * a forever-timer running). Mirrors the workspace's slow auto-refresh effect,
 * but on the ~2s cadence the in-flight queue needs.
 *
 * `onSettle` fires when the active-request count drops between polls, so the
 * workspace can refresh its transcript when verdicts land — the queue itself
 * does not need SSE; polling the list endpoint is sufficient.
 */
export function useEvaluationQueue(
  open: boolean,
  onSettle?: () => void
): EvaluationQueue {
  const [requests, setRequests] = useState<EvaluationQueueRequest[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The latest active count, read by the poll loop to decide whether to keep
  // ticking without re-subscribing the effect on every change.
  const activeCountRef = useRef(0);
  // Latest onSettle, so the stable fetch callback always calls the current one.
  // Synced in an effect (writing refs during render is disallowed).
  const onSettleRef = useRef(onSettle);
  useEffect(() => {
    onSettleRef.current = onSettle;
  }, [onSettle]);

  const fetchOnce = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await listEvaluations({ limit: QUEUE_LIMIT });
      const next = data.requests ?? [];
      const nextActive = countActiveRequests(next);
      if (nextActive < activeCountRef.current) {
        // A request transitioned to terminal since the last poll: verdicts may
        // have landed, so let the workspace refresh its transcript.
        onSettleRef.current?.();
      }
      activeCountRef.current = nextActive;
      setRequests(next);
      setError(null);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Failed to load the evaluations queue."
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  const refresh = useCallback(() => {
    void fetchOnce();
  }, [fetchOnce]);

  const cancel = useCallback(
    async (gameId: string, requestId: string) => {
      try {
        await cancelEvaluation(gameId, requestId);
      } catch (e) {
        setError(
          e instanceof Error ? e.message : "Failed to cancel the evaluation."
        );
      } finally {
        void fetchOnce();
      }
    },
    [fetchOnce]
  );

  const remove = useCallback(
    async (requestId: string) => {
      try {
        await deleteEvaluation(requestId);
      } catch (e) {
        // A 409 (the request is no longer terminal) surfaces here; the refresh
        // below re-reads the live status so the row reflects reality.
        setError(
          e instanceof Error ? e.message : "Failed to clear the evaluation."
        );
      } finally {
        void fetchOnce();
      }
    },
    [fetchOnce]
  );

  const clearTerminal = useCallback(async () => {
    try {
      await clearEvaluations();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to clear evaluations.");
    } finally {
      void fetchOnce();
    }
  }, [fetchOnce]);

  // A self-scheduling poll loop: fetch, then re-arm the next tick only while the
  // panel is open or work is in flight. Stops cleanly when both are false, so a
  // closed, idle queue holds no standing timer. `open` re-runs the effect so
  // opening the panel restarts polling immediately.
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = () => {
      void fetchOnce().finally(() => {
        if (cancelled) return;
        if (open || activeCountRef.current > 0) {
          timer = setTimeout(tick, POLL_INTERVAL_MS);
        }
      });
    };
    tick();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [fetchOnce, open]);

  return {
    requests,
    activeCount: countActiveRequests(requests),
    terminalCount: countTerminalRequests(requests),
    isLoading,
    error,
    refresh,
    cancel,
    remove,
    clearTerminal,
  };
}
