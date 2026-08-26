"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  GamePlatform,
  HistoryEvent,
  HistorySnapshot,
} from "@/features/shared/lib/types";
import {
  listAllHistoryTimeline,
  listHistorySnapshots,
} from "@/features/history/lib/history-api";

export interface UseHistoryResult {
  events: HistoryEvent[];
  snapshots: HistorySnapshot[];
  isLoading: boolean;
  error: string | null;
  /**
   * True when the client's safety bound stopped the walk before the game's log
   * ended, so `events` is a prefix of the timeline rather than all of it.
   */
  isTruncated: boolean;
  /** Reload the whole timeline from scratch. */
  reload: () => void;
  /**
   * Append whatever was recorded since the last load. History is append-only,
   * so this is what a poll or a tab refocus needs — re-reading the events
   * already held is pure waste and it grows with the length of the game.
   */
  refresh: () => void;
}

export function useHistory(
  gameId: string | null,
  platform: GamePlatform = "dragncards"
): UseHistoryResult {
  const [events, setEvents] = useState<HistoryEvent[]>([]);
  const [snapshots, setSnapshots] = useState<HistorySnapshot[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isTruncated, setIsTruncated] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  // A monotonic ticket for the incremental appends, so a slow one that resolves
  // after a reload (or a game switch) can be dropped instead of resurrecting a
  // stale timeline.
  const [refreshToken, setRefreshToken] = useState(0);
  const loadIdRef = useRef(0);
  // The resume point for an incremental append, mirrored into a ref so the
  // append effect can read it without depending on `events` — depending on
  // `events` would re-run the effect on every append and turn the poll into a
  // loop.
  const highestSeqRef = useRef(0);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);
  const refresh = useCallback(() => setRefreshToken((token) => token + 1), []);

  useEffect(() => {
    let cancelled = false;
    const loadId = loadIdRef.current + 1;
    loadIdRef.current = loadId;

    const load = async () => {
      highestSeqRef.current = 0;
      if (!gameId) {
        setEvents([]);
        setSnapshots([]);
        setIsTruncated(false);
        setError(null);
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      setError(null);
      try {
        const [timeline, loadedSnapshots] = await Promise.all([
          listAllHistoryTimeline(gameId, { platform }),
          listHistorySnapshots(gameId, platform),
        ]);
        if (cancelled) return;
        const ordered = [...timeline.events].sort((a, b) => a.seq - b.seq);
        highestSeqRef.current =
          ordered.length > 0 ? ordered[ordered.length - 1].seq : 0;
        setEvents(ordered);
        setIsTruncated(timeline.truncated);
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
  }, [gameId, platform, reloadToken]);

  // Incremental append: read only what was recorded after the highest seq
  // already held, and merge it in. Keyed off `refreshToken` alone.
  useEffect(() => {
    if (!gameId || refreshToken === 0) return;
    let cancelled = false;
    const loadId = loadIdRef.current;
    const afterSeq = highestSeqRef.current;

    const append = async () => {
      try {
        const timeline = await listAllHistoryTimeline(gameId, {
          afterSeq,
          platform,
        });
        // Drop a response that a reload or a game switch has made stale, rather
        // than letting it resurrect a timeline that has moved on.
        if (cancelled || loadIdRef.current !== loadId) return;
        if (timeline.events.length === 0) return;
        setEvents((current) => {
          const known = new Set(current.map((event) => event.seq));
          const added = timeline.events.filter(
            (event) => !known.has(event.seq)
          );
          if (added.length === 0) return current;
          const merged = [...current, ...added].sort((a, b) => a.seq - b.seq);
          highestSeqRef.current = merged[merged.length - 1].seq;
          return merged;
        });
      } catch {
        /* a background append is best-effort; the loaded timeline stands */
      }
    };
    append();

    return () => {
      cancelled = true;
    };
  }, [gameId, platform, refreshToken]);

  return { events, snapshots, isLoading, error, isTruncated, reload, refresh };
}
