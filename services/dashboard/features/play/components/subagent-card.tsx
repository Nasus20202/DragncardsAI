"use client";

import { Button, Card } from "@heroui/react";
import { useEffect, useRef, useState } from "react";
import { JobEventResponse } from "@/features/shared/lib/types";
import { getJobEvents } from "@/features/play/lib/client-api";
import {
  aggregateEvents,
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
    <Card className="overflow-hidden text-sm">
      {/* Header */}
      <Button
        fullWidth
        variant="ghost"
        className="h-auto min-h-0 items-center justify-start gap-2 rounded-none bg-transparent px-3 py-2 text-left"
        onPress={() => setCollapsed((c) => !c)}
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
      </Button>

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
                isLast={i === aggregated.length - 1}
              />
            ))
          )}
        </div>
      )}
    </Card>
  );
}
