"use client";

import { useEffect, useRef, useState } from "react";
import { JobEventResponse } from "@/features/shared/lib/types";
import { getJobEvents } from "@/features/play/lib/client-api";
import {
  aggregateEvents,
  SubagentEntry,
  upsertStreamEvent,
} from "@/features/play/lib/play-session-events";
import { AggEventRow } from "./play-transcript";

interface SubagentCardProps {
  childJobId: string;
  name: string;
  isRunning: boolean;
  /** Called when the child job's SSE stream receives a terminal event. */
  onFinished?: (childJobId: string, outcome: "completed" | "failed") => void;
}

const TERMINAL_TYPES = new Set(["completion", "failure", "cancellation"]);

export function SubagentCard({
  childJobId,
  name,
  isRunning,
  onFinished,
}: SubagentCardProps) {
  const [events, setEvents] = useState<JobEventResponse[]>([]);
  const [collapsed, setCollapsed] = useState(!isRunning);
  // `streaming` is the source of truth for live status — the isRunning prop
  // can go stale if the parent job hasn't re-fetched yet when the child finishes.
  const [streaming, setStreaming] = useState(isRunning);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!isRunning) {
      // Fetch stored events statically
      getJobEvents(childJobId)
        .then(setEvents)
        .catch(() => {});
      return;
    }

    // Open SSE stream for live events
    const source = new EventSource(
      `/api/proxy/orchestrator/jobs/${childJobId}/events/stream?after=0`
    );
    sourceRef.current = source;

    // Use ONLY named event listeners (never "message") to avoid double-firing.
    // The server sends each event with its event_type as the SSE event name.
    const handleEvent = (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as JobEventResponse;
        setEvents((prev) => upsertStreamEvent(prev, data));
        if (TERMINAL_TYPES.has(data.event_type)) {
          setStreaming(false);
          setCollapsed(true);
          source.close();
          sourceRef.current = null;
          onFinished?.(
            childJobId,
            data.event_type === "completion" ? "completed" : "failed"
          );
        }
      } catch {
        // ignore parse errors
      }
    };

    const eventTypes = [
      "progress",
      "reasoning",
      "model_output",
      "tool_call",
      "tool_result",
      "skill_loaded",
      "subagent_started",
      "subagent_completed",
      "subagent_failed",
      "completion",
      "failure",
      "cancellation",
      "compaction",
    ];
    for (const type of eventTypes) {
      source.addEventListener(type, handleEvent as EventListener);
    }

    source.onerror = () => {
      setStreaming(false);
    };

    return () => {
      source.close();
      sourceRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [childJobId]); // intentionally omit isRunning — streaming state is managed internally

  const aggregated = aggregateEvents(events, false);
  const hasOutput = aggregated.some((a) => a.kind === "model_output");

  return (
    <div className="rounded-lg border border-default-200 bg-default-50 text-sm">
      {/* Header */}
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
        onClick={() => setCollapsed((c) => !c)}
      >
        {streaming ? (
          <span className="inline-block h-2 w-2 shrink-0 animate-pulse rounded-full bg-success-500" />
        ) : (
          <span className="inline-block h-2 w-2 shrink-0 rounded-full bg-default-400" />
        )}
        <span className="flex-1 truncate font-medium text-default-700">
          {name}
        </span>
        <span className="text-default-400">{collapsed ? "▸" : "▾"}</span>
      </button>

      {/* Body */}
      {!collapsed && (
        <div className="border-t border-default-200 px-3 py-2 space-y-1">
          {aggregated.length === 0 ? (
            <p className="text-xs text-default-400 italic">
              Waiting for events…
            </p>
          ) : (
            aggregated.map((agg, i) => (
              <AggEventRow
                key={i}
                agg={agg}
                isStreaming={streaming}
                hasOutput={hasOutput}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}

/* ── Collapsible list of subagent cards ──────────────────────────── */

export function SubagentList({
  entries,
  onSubagentFinished,
}: {
  entries: SubagentEntry[];
  onSubagentFinished?: (
    childJobId: string,
    outcome: "completed" | "failed"
  ) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  const liveEntries = entries.filter((e) => e.status === "running");
  const visible = expanded ? entries : liveEntries;

  // If nothing to show at all, render nothing
  if (entries.length === 0) return null;

  return (
    <div className="shrink-0 border-t border-default-100">
      {/* Header row */}
      <button
        type="button"
        className="flex w-full items-center justify-between px-4 py-1.5 text-xs text-default-400 hover:text-default-600"
        onClick={() => setExpanded((e) => !e)}
      >
        <span className="font-medium uppercase tracking-wider">
          Subagents
          {liveEntries.length > 0 && (
            <span className="ml-1.5 inline-flex items-center gap-1">
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-success-500" />
              {liveEntries.length} running
            </span>
          )}
          {!expanded && liveEntries.length === 0 && (
            <span className="ml-1.5 text-default-300">
              {entries.length} done
            </span>
          )}
        </span>
        <span aria-hidden="true">{expanded ? "▴" : "▾"}</span>
      </button>

      {/* Cards */}
      {visible.length > 0 && (
        <div className="space-y-2 overflow-y-auto px-4 pb-2 max-h-64">
          {visible.map((entry) => (
            <SubagentCard
              key={entry.childJobId}
              childJobId={entry.childJobId}
              name={entry.name ?? entry.childJobId.slice(0, 8)}
              isRunning={entry.status === "running"}
              onFinished={onSubagentFinished}
            />
          ))}
        </div>
      )}
    </div>
  );
}
