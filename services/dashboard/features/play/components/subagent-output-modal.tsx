"use client";

import { useEffect, useRef, useState } from "react";
import { JobEventResponse } from "@/features/shared/lib/types";
import { getJobEvents } from "@/features/play/lib/client-api";
import {
  aggregateEvents,
  upsertStreamEvent,
} from "@/features/play/lib/play-session-events";
import { redactSecrets } from "@/features/play/lib/tool-call-presentation";
import { AggEventRow } from "@/features/play/components/play-transcript";

const TERMINAL_TYPES = new Set(["completion", "failure", "cancellation"]);

const ALL_EVENT_TYPES = [
  "progress",
  "reasoning",
  "model_output",
  "compaction",
  "tool_call",
  "tool_result",
  "completion",
  "failure",
  "cancellation",
  "skill_loaded",
  "subagent_started",
  "subagent_completed",
  "subagent_failed",
];

export function SubagentOutputModal({
  childJobId,
  name,
  isRunning,
  onClose,
}: {
  childJobId: string;
  name: string;
  isRunning: boolean;
  onClose: () => void;
}) {
  const [events, setEvents] = useState<JobEventResponse[]>([]);
  const [done, setDone] = useState(!isRunning);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isRunning) {
      getJobEvents(childJobId)
        .then((evts) => {
          setEvents(evts);
          setDone(true);
        })
        .catch(() => {});
      return;
    }

    const url = `/api/proxy/orchestrator/jobs/${childJobId}/events/stream?after=0`;
    const source = new EventSource(url);

    const handler = (ev: MessageEvent) => {
      try {
        const parsed: JobEventResponse = JSON.parse(ev.data);
        setEvents((prev) => upsertStreamEvent(prev, parsed));
        if (TERMINAL_TYPES.has(parsed.event_type)) {
          setDone(true);
          source.close();
        }
      } catch {
        /* ignore */
      }
    };

    // Named listeners only — no source.onmessage to avoid duplicates
    for (const t of ALL_EVENT_TYPES) {
      source.addEventListener(t, handler as EventListener);
    }

    return () => source.close();
  }, [childJobId, isRunning]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [events]);

  const aggEvents = aggregateEvents(events, false);
  const hasOutput = aggEvents.some((e) => e.kind === "model_output");

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-label="Subagent output"
      onClick={onClose}
    >
      <div
        className="relative flex h-[80vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-default-200 bg-background shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex h-10 shrink-0 items-center justify-between border-b border-default-200/60 px-4">
          <div className="flex items-center gap-2">
            {!done && (
              <svg
                className="h-3 w-3 shrink-0 animate-spin text-success-500"
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden="true"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
                />
              </svg>
            )}
            {/*
              Redacted like every other displayed name: a subagent recorded
              before the orchestrator generated names carries a raw slice of a
              model-written prompt, and stored events are replayed forever.
            */}
            <span className="text-xs font-semibold text-default-500">
              {redactSecrets(name)}
            </span>
          </div>
          <button
            type="button"
            aria-label="Close subagent output"
            className="rounded px-2 py-1 text-xs text-default-400 hover:bg-default-100 hover:text-foreground"
            onClick={onClose}
          >
            ✕
          </button>
        </div>

        {/* Transcript-style events */}
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-3xl px-4 py-6">
            {aggEvents.length === 0 ? (
              <p className="text-xs text-default-400">
                {done ? "No output." : "Waiting for output…"}
              </p>
            ) : (
              <div className="space-y-2">
                {aggEvents.map((agg, i) => (
                  <AggEventRow
                    key={i}
                    agg={agg}
                    isStreaming={!done}
                    hasOutput={hasOutput}
                    isLast={i === aggEvents.length - 1}
                  />
                ))}
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>
      </div>
    </div>
  );
}
