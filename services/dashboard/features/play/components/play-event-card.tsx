"use client";

import { JobEventResponse } from "@/features/shared/lib/types";
import { useState } from "react";

const LABELS: Record<string, string> = {
  model_output:  "Assistant",
  reasoning:     "Reasoning",
  progress:      "Progress",
  tool_call:     "Tool call",
  tool_result:   "Tool result",
  completion:    "Done",
  failure:       "Error",
  cancellation:  "Cancelled",
};

function bodyText(event: JobEventResponse): string {
  const p = event.payload;
  if (typeof p.text === "string")    return p.text;
  if (typeof p.message === "string") return p.message;
  if (typeof p.status === "string")  return p.status;
  return JSON.stringify(p, null, 2);
}

function hhmm(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/* ── Individual event renderers ──────────────────────────────────── */

function AssistantMessage({ text }: { text: string }) {
  return (
    <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
      {text}
    </p>
  );
}

function ErrorMessage({ text, time }: { text: string; time: string }) {
  return (
    <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm">
      <span className="mr-1.5 font-semibold text-danger">Error</span>
      <span className="text-danger/80">{text}</span>
      <span className="ml-2 text-xs text-danger/50">{time}</span>
    </div>
  );
}

function CancelledNote({ time }: { time: string }) {
  return (
    <p className="text-xs italic text-default-400">
      Cancelled at {time}
    </p>
  );
}

function CollapsibleCard({ event }: { event: JobEventResponse }) {
  const [open, setOpen] = useState(false);
  const label = LABELS[event.event_type] ?? event.event_type;
  const time  = hhmm(event.created_at);

  const dotClass =
    event.event_type === "reasoning"  ? "bg-warning" :
    event.event_type === "progress"   ? "bg-accent"  :
    event.event_type === "tool_call"  ? "bg-default-400" :
    "bg-default-300";

  return (
    <div className="overflow-hidden rounded-lg border border-default-200/60 bg-default-50/40 dark:bg-white/3">
      <button
        type="button"
        aria-expanded={open}
        aria-label={`${open ? "Collapse" : "Expand"} ${label}`}
        className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left transition-colors hover:bg-default-100/60"
        onClick={() => setOpen((p) => !p)}
      >
        <div className="flex items-center gap-2">
          <span aria-hidden="true" className={`h-1.5 w-1.5 shrink-0 rounded-full ${dotClass}`} />
          <span className="text-xs font-medium text-default-500">{label}</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-default-400">
          <span>{time}</span>
          <span aria-hidden="true">{open ? "▴" : "▾"}</span>
        </div>
      </button>

      {open && (
        <div className="border-t border-default-200/60 px-3 py-2.5">
          <pre className="overflow-x-auto whitespace-pre-wrap text-xs leading-relaxed text-default-600 dark:text-default-300">
            {bodyText(event)}
          </pre>
        </div>
      )}
    </div>
  );
}

/* ── Public component ─────────────────────────────────────────────── */

export function PlayEventCard({ event }: { event: JobEventResponse }) {
  const time = hhmm(event.created_at);

  switch (event.event_type) {
    case "model_output":
      return <AssistantMessage text={bodyText(event)} />;

    case "completion":
      // Completion is silent — model_output already carries the text.
      return null;

    case "failure":
      return <ErrorMessage text={bodyText(event)} time={time} />;

    case "cancellation":
      return <CancelledNote time={time} />;

    case "reasoning":
    case "progress":
    case "tool_call":
    case "tool_result":
      return <CollapsibleCard event={event} />;

    default:
      // Unknown event — show as plain collapsible
      return <CollapsibleCard event={event} />;
  }
}
