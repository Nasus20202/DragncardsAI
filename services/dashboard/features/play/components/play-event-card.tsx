"use client";

import { CollapsibleCard as SharedCollapsibleCard } from "@/features/shared/components/collapsible-card";
import { JobEventResponse } from "@/features/shared/lib/types";

const LABELS: Record<string, string> = {
  model_output: "Assistant",
  reasoning: "Reasoning",
  progress: "Progress",
  tool_call: "Tool call",
  compaction: "Context compaction",
  tool_result: "Tool result",
  completion: "Done",
  failure: "Error",
  cancellation: "Cancelled",
  skill_loaded: "Skill loaded",
  subagent_started: "Subagent started",
  subagent_completed: "Subagent completed",
  subagent_failed: "Subagent failed",
};

function bodyText(event: JobEventResponse): string {
  const p = event.payload;
  if (typeof p.text === "string") return p.text;
  if (typeof p.summary_text === "string") return p.summary_text;
  if (typeof p.message === "string") return p.message;
  if (typeof p.status === "string") return p.status;
  return JSON.stringify(p, null, 2);
}

function hhmm(iso: string) {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
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
  return <p className="text-xs italic text-default-400">Cancelled at {time}</p>;
}

function CollapsibleCard({ event }: { event: JobEventResponse }) {
  const label = LABELS[event.event_type] ?? event.event_type;
  const time = hhmm(event.created_at);

  const dotClass =
    event.event_type === "reasoning"
      ? "bg-warning"
      : event.event_type === "progress"
        ? "bg-accent"
        : event.event_type === "compaction"
          ? "bg-secondary"
          : event.event_type === "tool_call"
            ? "bg-default-400"
            : "bg-default-300";

  return (
    <SharedCollapsibleCard
      label={label}
      dotClass={dotClass}
      body={bodyText(event)}
      time={time}
    />
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
    case "compaction":
    case "tool_call":
    case "tool_result":
    case "skill_loaded":
      return <CollapsibleCard event={event} />;

    case "subagent_started":
    case "subagent_completed":
    case "subagent_failed": {
      const label = LABELS[event.event_type] ?? event.event_type;
      const childId =
        typeof event.payload.child_job_id === "string"
          ? event.payload.child_job_id
          : "";
      return (
        <p className="text-xs text-default-400">
          {label}
          {childId ? `: ${childId.slice(0, 8)}…` : ""}
        </p>
      );
    }

    default:
      // Unknown event — show as plain collapsible
      return <CollapsibleCard event={event} />;
  }
}
