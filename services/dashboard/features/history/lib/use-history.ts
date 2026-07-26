"use client";

import { useCallback, useEffect, useState } from "react";

import { HistoryEvent, HistorySnapshot } from "@/features/shared/lib/types";
import {
  listHistoryEvents,
  listHistorySnapshots,
} from "@/features/history/lib/history-api";

export interface UseHistoryResult {
  events: HistoryEvent[];
  snapshots: HistorySnapshot[];
  isLoading: boolean;
  error: string | null;
  reload: () => void;
}

export function useHistory(gameId: string | null): UseHistoryResult {
  const [events, setEvents] = useState<HistoryEvent[]>([]);
  const [snapshots, setSnapshots] = useState<HistorySnapshot[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      if (!gameId) {
        setEvents([]);
        setSnapshots([]);
        setError(null);
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      setError(null);
      try {
        const [loadedEvents, loadedSnapshots] = await Promise.all([
          listHistoryEvents(gameId),
          listHistorySnapshots(gameId),
        ]);
        if (cancelled) return;
        setEvents([...loadedEvents].sort((a, b) => a.seq - b.seq));
        setSnapshots(loadedSnapshots);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Failed to load history");
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };
    load();

    return () => {
      cancelled = true;
    };
  }, [gameId, reloadToken]);

  return { events, snapshots, isLoading, error, reload };
}
