"use client";

import { useEffect, useRef } from "react";
import { useState } from "react";
import { Tooltip } from "@heroui/react";
import { SubagentEntry } from "@/features/play/lib/subagents";

interface Props {
  entries: SubagentEntry[];
  onSelect: (entry: SubagentEntry) => void;
  onSubagentFinished?: (
    childJobId: string,
    outcome: "completed" | "failed"
  ) => void;
}

const TERMINAL_EVENT_TYPES = new Set(["completion", "failure", "cancellation"]);
const BURGER_STREAM_EVENT_TYPES = [
  "completion",
  "failure",
  "cancellation",
] as const;

/**
 * Subscribes to a running child job's SSE stream and fires `onFinished`
 * when a terminal event arrives. Renders nothing — side-effect only.
 */
function ChildJobWatcher({
  childJobId,
  onFinished,
}: {
  childJobId: string;
  onFinished: (childJobId: string, outcome: "completed" | "failed") => void;
}) {
  const calledRef = useRef(false);

  useEffect(() => {
    calledRef.current = false;
    const source = new EventSource(
      `/api/proxy/orchestrator/jobs/${childJobId}/events/stream?after=0`
    );

    const handle = (ev: MessageEvent) => {
      try {
        const data = JSON.parse(ev.data) as { event_type: string };
        if (TERMINAL_EVENT_TYPES.has(data.event_type) && !calledRef.current) {
          calledRef.current = true;
          source.close();
          onFinished(
            childJobId,
            data.event_type === "completion" ? "completed" : "failed"
          );
        }
      } catch {
        /* ignore */
      }
    };

    for (const t of BURGER_STREAM_EVENT_TYPES) {
      source.addEventListener(t, handle as EventListener);
    }

    source.onerror = () => {
      source.close();
    };

    return () => source.close();
  }, [childJobId, onFinished]);

  return null;
}

function Spinner() {
  return (
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
  );
}

function StatusIcon({ status }: { status: SubagentEntry["status"] }) {
  if (status === "running") return <Spinner />;
  if (status === "failed")
    return (
      <span className="h-3 w-3 shrink-0 text-center text-[10px] leading-none text-danger-500">
        ✕
      </span>
    );
  return (
    <span className="h-3 w-3 shrink-0 text-center text-[10px] leading-none text-success-500">
      ✓
    </span>
  );
}

function EntryRow({
  entry,
  onSelect,
}: {
  entry: SubagentEntry;
  onSelect: (e: SubagentEntry) => void;
}) {
  const button = (
    <button
      type="button"
      onClick={() => onSelect(entry)}
      className={[
        "flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs shadow-sm backdrop-blur-sm",
        entry.status === "failed"
          ? "border-danger-200 bg-danger-50/90 hover:bg-danger-100"
          : "border-default-200 bg-content1/95 hover:bg-default-100",
      ].join(" ")}
    >
      <StatusIcon status={entry.status} />
      <span className="max-w-[140px] truncate text-default-600">
        {entry.name ?? entry.childJobId.slice(0, 8)}
      </span>
    </button>
  );

  if (entry.status === "failed" && entry.reason) {
    return (
      <Tooltip delay={200}>
        <Tooltip.Trigger>{button}</Tooltip.Trigger>
        <Tooltip.Content placement="left">
          <p className="text-xs">Failed: {entry.reason}</p>
        </Tooltip.Content>
      </Tooltip>
    );
  }

  return button;
}

export function SubagentBurger({
  entries,
  onSelect,
  onSubagentFinished,
}: Props) {
  const [expanded, setExpanded] = useState(false);

  const running = entries.filter((e) => e.status === "running");
  const failed = entries.filter((e) => e.status === "failed");
  // Default: show running + failed; all when expanded
  const visible = expanded ? entries : [...running, ...failed];

  if (entries.length === 0) return null;

  return (
    <div className="flex flex-col items-end gap-0.5">
      {/* Watch all running child jobs so the burger updates without waiting for
          the parent job's subagent_completed / subagent_failed event. */}
      {onSubagentFinished &&
        running.map((e) => (
          <ChildJobWatcher
            key={e.childJobId}
            childJobId={e.childJobId}
            onFinished={onSubagentFinished}
          />
        ))}

      {/* Group header — always visible */}
      <div className="flex items-center gap-1.5 px-1">
        {failed.length > 0 && !expanded && (
          <span className="text-[10px] font-medium text-danger-500">
            {failed.length} failed
          </span>
        )}
        <span className="text-[10px] font-semibold uppercase tracking-wider text-default-400">
          Subagents
        </span>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="rounded px-1 py-0.5 text-[10px] text-default-400 hover:bg-default-100 hover:text-default-600"
          aria-label={expanded ? "Collapse subagents" : "Expand subagents"}
        >
          {expanded ? "▴" : `▾ ${entries.length}`}
        </button>
      </div>

      {/* Rows */}
      {visible.length > 0 && (
        <div className="flex flex-col items-end gap-0.5">
          {visible.map((entry) => (
            <EntryRow
              key={entry.childJobId}
              entry={entry}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}
