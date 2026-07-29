"use client";

import { useEffect, useMemo, useRef } from "react";
import { useState } from "react";
import { ToggleButton, ToggleButtonGroup, Tooltip } from "@heroui/react";
import { SubagentEntry } from "@/features/play/lib/play-session-events";
import { redactSecrets } from "@/features/play/lib/tool-call-presentation";
import {
  DEFAULT_SUBAGENT_STATUS_FILTER,
  SUBAGENT_STATUS_FILTERS,
  SubagentStatusFilter,
  attentionSubagents,
  countSubagentsByStatus,
  filterSubagentsByStatus,
  isSubagentStatusFilter,
} from "@/features/play/lib/subagent-filter";

interface Props {
  entries: SubagentEntry[];
  onSelect: (entry: SubagentEntry) => void;
  onSubagentFinished?: (
    childJobId: string,
    outcome: "completed" | "failed"
  ) => void;
}

const TERMINAL_EVENT_TYPES = new Set(["completion", "failure", "cancellation"]);
const SUBAGENT_STREAM_EVENT_TYPES = [
  "completion",
  "failure",
  "cancellation",
] as const;

/**
 * Subscribes to a running child job's SSE stream and fires `onFinished`
 * when a terminal event arrives. Renders nothing; side-effect only.
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

    for (const eventType of SUBAGENT_STREAM_EVENT_TYPES) {
      source.addEventListener(eventType, handle as EventListener);
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
  if (status === "failed") {
    return (
      <span className="h-3 w-3 shrink-0 text-center text-[10px] leading-none text-danger-500">
        X
      </span>
    );
  }
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
  // A generated name is longer than the row, so the full one is available as a
  // title. The short job id remains the fallback for an entry that has no name.
  //
  // Redacted for the same reason the tool cards redact: a name recorded before
  // the orchestrator generated them is a raw slice of a model-written prompt, and
  // those are replayed from storage indefinitely.
  const label = redactSecrets(entry.name ?? entry.childJobId.slice(0, 8));
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
      <span className="max-w-[180px] truncate text-default-600" title={label}>
        {label}
      </span>
    </button>
  );

  if (entry.status === "failed" && entry.reason) {
    return (
      <Tooltip delay={200}>
        <Tooltip.Trigger>{button}</Tooltip.Trigger>
        <Tooltip.Content placement="left">
          <p className="text-xs">Failed: {redactSecrets(entry.reason)}</p>
        </Tooltip.Content>
      </Tooltip>
    );
  }

  return button;
}

/**
 * Status filter for the expanded list. A new sub-control, so it is built from
 * Hero UI's `ToggleButtonGroup` rather than hand-rolled — and sized down to the
 * 10px chrome of the list it sits in, so it reads as part of that list and not
 * as a form dropped on top of the transcript.
 */
function StatusFilterBar({
  counts,
  value,
  onChange,
}: {
  counts: Record<SubagentStatusFilter, number>;
  value: SubagentStatusFilter;
  onChange: (next: SubagentStatusFilter) => void;
}) {
  return (
    <ToggleButtonGroup
      aria-label="Filter subagents by status"
      data-testid="subagent-status-filter"
      selectionMode="single"
      disallowEmptySelection
      selectedKeys={[value]}
      onSelectionChange={(keys) => {
        const [next] = Array.from(keys);
        if (isSubagentStatusFilter(next)) {
          onChange(next);
        }
      }}
      size="sm"
      className="bg-content1/95 shadow-sm backdrop-blur-sm"
    >
      {SUBAGENT_STATUS_FILTERS.map((option) => (
        <ToggleButton
          key={option.key}
          id={option.key}
          variant="ghost"
          className="h-6 min-w-0 px-2 text-[10px] font-medium"
        >
          {`${option.label} ${counts[option.key]}`}
        </ToggleButton>
      ))}
    </ToggleButtonGroup>
  );
}

export function SubagentList({ entries, onSelect, onSubagentFinished }: Props) {
  const [expanded, setExpanded] = useState(false);
  // View state only: which statuses the reader is currently looking at is not
  // worth persisting anywhere, and deliberately resets with the component.
  const [statusFilter, setStatusFilter] = useState<SubagentStatusFilter>(
    DEFAULT_SUBAGENT_STATUS_FILTER
  );

  const running = useMemo(
    () => entries.filter((entry) => entry.status === "running"),
    [entries]
  );
  const counts = useMemo(() => countSubagentsByStatus(entries), [entries]);
  const visible = expanded
    ? filterSubagentsByStatus(entries, statusFilter)
    : attentionSubagents(entries);

  if (entries.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-col items-end gap-0.5">
      {/* Watch running child jobs so the list updates immediately. */}
      {onSubagentFinished &&
        running.map((entry) => (
          <ChildJobWatcher
            key={entry.childJobId}
            childJobId={entry.childJobId}
            onFinished={onSubagentFinished}
          />
        ))}

      <div className="flex items-center gap-1.5 px-1">
        {counts.failed > 0 && !expanded && (
          <span className="text-[10px] font-medium text-danger-500">
            {counts.failed} failed
          </span>
        )}
        <span className="text-[10px] font-semibold uppercase tracking-wider text-default-400">
          Subagents
        </span>
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="rounded px-1 py-0.5 text-[10px] text-default-400 hover:bg-default-100 hover:text-default-600"
          aria-label={expanded ? "Collapse subagents" : "Expand subagents"}
        >
          {expanded ? "▴" : `▾ ${entries.length}`}
        </button>
      </div>

      {expanded && (
        <StatusFilterBar
          counts={counts}
          value={statusFilter}
          onChange={setStatusFilter}
        />
      )}

      {/*
        The list scrolls inside its own box. It floats over the transcript with
        nothing below it to push, so an unbounded list simply ran off the bottom
        of the viewport and took its last entries with it — the height cap is
        what makes the entries beyond it reachable at all.
      */}
      {visible.length > 0 ? (
        <div
          data-testid="subagent-list-scroll"
          className="flex max-h-[min(45vh,16rem)] flex-col items-end gap-0.5 overflow-y-auto overscroll-contain pr-0.5"
        >
          {visible.map((entry) => (
            <EntryRow
              key={entry.childJobId}
              entry={entry}
              onSelect={onSelect}
            />
          ))}
        </div>
      ) : (
        expanded && (
          <span
            data-testid="subagent-list-empty"
            className="px-1 py-0.5 text-[10px] text-default-400"
          >
            No subagents with this status
          </span>
        )
      )}
    </div>
  );
}
