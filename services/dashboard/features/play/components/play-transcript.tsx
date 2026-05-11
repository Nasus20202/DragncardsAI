import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  JobEventResponse,
  JobDetail,
  SessionDetail,
} from "@/features/shared/lib/types";
import { useEffect, useRef, useState } from "react";

/* ── Aggregated view types ───────────────────────────────────────── */

type AggEvent =
  | { kind: "reasoning"; text: string }
  | { kind: "model_output"; text: string }
  | { kind: "compaction"; text: string }
  | { kind: "tool_call"; event: JobEventResponse }
  | { kind: "tool_result"; event: JobEventResponse }
  | { kind: "failure"; event: JobEventResponse }
  | { kind: "cancellation"; event: JobEventResponse };

function compactionText(event: JobEventResponse): string {
  if (typeof event.payload.summary_text === "string") {
    return event.payload.summary_text;
  }
  if (typeof event.payload.text === "string") {
    return event.payload.text;
  }
  return JSON.stringify(event.payload, null, 2);
}

/**
 * Collapse raw events into a display list:
 *  - progress (queued/running) → dropped entirely
 *  - completion → final assistant text, replacing any partial streamed output
 *  - reasoning → all chunks merged into one string
 *  - model_output → all chunks merged into one string
 *  - everything else → kept as-is
 */
function aggregateEvents(
  events: JobEventResponse[],
  isCompactionJob: boolean
): AggEvent[] {
  let reasoningText = "";
  let modelText = "";
  const result: AggEvent[] = [];

  function flushReasoning() {
    if (reasoningText) {
      result.push({ kind: "reasoning", text: reasoningText });
      reasoningText = "";
    }
  }
  function flushModel() {
    if (modelText) {
      result.push({ kind: "model_output", text: modelText });
      modelText = "";
    }
  }

  for (const ev of events) {
    switch (ev.event_type) {
      case "progress":
        break;

      case "completion": {
        flushReasoning();
        const completionText =
          typeof ev.payload.text === "string" ? ev.payload.text : "";
        if (completionText) {
          modelText = completionText;
        }
        break;
      }

      case "reasoning":
        reasoningText +=
          typeof ev.payload.text === "string" ? ev.payload.text : "";
        break;

      case "model_output":
        if (isCompactionJob || eventHasCompactionPayload(ev)) {
          flushReasoning();
          flushModel();
          result.push({ kind: "compaction", text: compactionText(ev) });
          break;
        }
        flushReasoning();
        modelText += typeof ev.payload.text === "string" ? ev.payload.text : "";
        break;

      case "tool_call":
        flushReasoning();
        flushModel();
        result.push({ kind: "tool_call", event: ev });
        break;

      case "compaction":
        flushReasoning();
        flushModel();
        result.push({ kind: "compaction", text: compactionText(ev) });
        break;

      case "tool_result":
        flushReasoning();
        flushModel();
        result.push({ kind: "tool_result", event: ev });
        break;

      case "failure":
        flushReasoning();
        flushModel();
        result.push({ kind: "failure", event: ev });
        break;

      case "cancellation":
        flushReasoning();
        flushModel();
        result.push({ kind: "cancellation", event: ev });
        break;

      default:
        flushReasoning();
        flushModel();
        result.push({ kind: "tool_call", event: ev });
        break;
    }
  }

  flushReasoning();
  flushModel();
  return result;
}

function eventHasCompactionPayload(event: JobEventResponse): boolean {
  return event.payload.compaction === true;
}

/* ── Sub-renderers ───────────────────────────────────────────────── */

/**
 * Reasoning block — open while the job is streaming, auto-collapses once
 * a model_output event has arrived (meaning the response is ready).
 */
function ReasoningBlock({
  text,
  isStreaming,
  hasOutput,
}: {
  text: string;
  isStreaming: boolean;
  hasOutput: boolean;
}) {
  // Start open; collapse automatically when the response arrives.
  const [open, setOpen] = useState(true);
  const prevHasOutput = useRef(hasOutput);

  useEffect(() => {
    // Auto-collapse the first time hasOutput flips from false → true
    if (!prevHasOutput.current && hasOutput) {
      setOpen(false);
    }
    prevHasOutput.current = hasOutput;
  }, [hasOutput]);

  return (
    <div className="overflow-hidden rounded-lg border border-default-200/60 bg-default-50/40 dark:bg-white/3">
      <button
        type="button"
        aria-expanded={open}
        aria-label={open ? "Collapse reasoning" : "Expand reasoning"}
        className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left transition-colors hover:bg-default-100/60"
        onClick={() => setOpen((p) => !p)}
      >
        <div className="flex items-center gap-2">
          {isStreaming && !hasOutput ? (
            <span
              aria-hidden="true"
              className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-warning"
            />
          ) : (
            <span
              aria-hidden="true"
              className="h-1.5 w-1.5 shrink-0 rounded-full bg-warning/60"
            />
          )}
          <span className="text-xs font-medium text-default-500">
            Reasoning
          </span>
        </div>
        <span aria-hidden="true" className="text-xs text-default-400">
          {open ? "▴" : "▾"}
        </span>
      </button>
      {open && (
        <div className="border-t border-default-200/60 px-3 py-2.5">
          <pre className="overflow-x-auto whitespace-pre-wrap text-xs leading-relaxed text-default-600 dark:text-default-300">
            {text}
          </pre>
        </div>
      )}
    </div>
  );
}

function CompactionBlock({ text }: { text: string }) {
  const [open, setOpen] = useState(true);

  return (
    <div className="overflow-hidden rounded-lg border border-default-200/60 bg-default-50/40 dark:bg-white/3">
      <button
        type="button"
        aria-expanded={open}
        aria-label={open ? "Collapse compaction" : "Expand compaction"}
        className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left transition-colors hover:bg-default-100/60"
        onClick={() => setOpen((p) => !p)}
      >
        <div className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className="h-1.5 w-1.5 shrink-0 rounded-full bg-warning/60"
          />
          <span className="text-xs font-medium text-default-500">
            Context compaction
          </span>
        </div>
        <span aria-hidden="true" className="text-xs text-default-400">
          {open ? "▴" : "▾"}
        </span>
      </button>
      {open && (
        <div className="border-t border-default-200/60 px-3 py-2.5">
          <pre className="overflow-x-auto whitespace-pre-wrap text-xs leading-relaxed text-default-600 dark:text-default-300">
            {text}
          </pre>
        </div>
      )}
    </div>
  );
}

function ModelOutputBlock({ text }: { text: string }) {
  return (
    <div className="prose prose-sm dark:prose-invert max-w-none text-base leading-relaxed text-foreground [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{ script: () => null }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

function CollapsibleEventBlock({
  label,
  dotClass,
  event,
}: {
  label: string;
  dotClass: string;
  event: JobEventResponse;
}) {
  const [open, setOpen] = useState(false);

  function bodyText(): string {
    const p = event.payload;
    if (typeof p.text === "string") return p.text;
    if (typeof p.summary_text === "string") return p.summary_text;
    if (typeof p.message === "string") return p.message;
    return JSON.stringify(p, null, 2);
  }

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
          <span
            aria-hidden="true"
            className={`h-1.5 w-1.5 shrink-0 rounded-full ${dotClass}`}
          />
          <span className="text-xs font-medium text-default-500">{label}</span>
        </div>
        <span aria-hidden="true" className="text-xs text-default-400">
          {open ? "▴" : "▾"}
        </span>
      </button>
      {open && (
        <div className="border-t border-default-200/60 px-3 py-2.5">
          <pre className="overflow-x-auto whitespace-pre-wrap text-xs leading-relaxed text-default-600 dark:text-default-300">
            {bodyText()}
          </pre>
        </div>
      )}
    </div>
  );
}

function AggEventRow({
  agg,
  isStreaming,
  hasOutput,
}: {
  agg: AggEvent;
  isStreaming: boolean;
  hasOutput: boolean;
}) {
  switch (agg.kind) {
    case "reasoning":
      return (
        <ReasoningBlock
          text={agg.text}
          isStreaming={isStreaming}
          hasOutput={hasOutput}
        />
      );
    case "model_output":
      return <ModelOutputBlock text={agg.text} />;
    case "tool_call":
      return (
        <CollapsibleEventBlock
          label={`Tool call: ${typeof agg.event.payload.exposed_tool_name === "string" ? agg.event.payload.exposed_tool_name : agg.event.event_type}`}
          dotClass="bg-default-400"
          event={agg.event}
        />
      );
    case "compaction":
      return <CompactionBlock text={agg.text} />;
    case "tool_result":
      return (
        <CollapsibleEventBlock
          label={`Tool result: ${typeof agg.event.payload.exposed_tool_name === "string" ? agg.event.payload.exposed_tool_name : agg.event.event_type}`}
          dotClass="bg-default-300"
          event={agg.event}
        />
      );
    case "failure":
      return (
        <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm">
          <span className="mr-1.5 font-semibold text-danger">Error</span>
          <span className="text-danger/80">
            {typeof agg.event.payload.message === "string"
              ? agg.event.payload.message
              : JSON.stringify(agg.event.payload)}
          </span>
        </div>
      );
    case "cancellation":
      return <p className="text-xs italic text-default-400">Cancelled</p>;
  }
}

/* ── One prompt + its events ─────────────────────────────────────── */
function JobThread({
  job,
  isStreaming,
}: {
  job: JobDetail;
  isStreaming: boolean;
}) {
  const isCompactionJob = job.prompt_run.prompt === "[COMPACTION]";
  const aggEvents = aggregateEvents(job.events, isCompactionJob);
  const isWaiting = job.events.length === 0;
  const hasOutput = aggEvents.some((e) => e.kind === "model_output");

  return (
    <div className="mb-8 space-y-3">
      {!isCompactionJob && (
        <div className="flex justify-end">
          <div className="max-w-[78%] rounded-2xl rounded-tr-sm bg-default-100 px-4 py-2.5 text-base leading-relaxed text-foreground dark:bg-white/6">
            {job.prompt_run.prompt}
          </div>
        </div>
      )}

      {/* Agent response */}
      {isWaiting ? (
        <div className="flex items-center gap-2 text-xs text-default-400">
          <span
            aria-hidden="true"
            className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-default-400"
          />
          Waiting for response…
        </div>
      ) : (
        <div className="space-y-2">
          {aggEvents.map((agg, i) => (
            <AggEventRow
              key={i}
              agg={agg}
              isStreaming={isStreaming}
              hasOutput={hasOutput}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Empty state ─────────────────────────────────────────────────── */
function Empty({ message }: { message: string }) {
  return (
    <div className="flex h-full min-h-32 items-center justify-center">
      <p className="text-sm text-default-400">{message}</p>
    </div>
  );
}

/* ── Main transcript ─────────────────────────────────────────────── */
export function PlayTranscript({
  jobs,
  streamingJobId,
  selectedSession,
  streamState,
  statusText,
  isBusy,
  errorText,
  onOpenSettings,
  settingsOpen,
}: {
  jobs: JobDetail[];
  streamingJobId: string | null;
  selectedSession: SessionDetail | null;
  streamState: "idle" | "streaming";
  statusText: string;
  isBusy: boolean;
  errorText: string | null;
  onOpenSettings: () => void;
  settingsOpen: boolean;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [jobs]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Status bar */}
      <div className="flex h-10 shrink-0 items-center justify-between border-b border-default-200/60 px-4">
        <div className="flex items-center gap-2">
          {streamState === "streaming" && (
            <span
              aria-hidden="true"
              className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-success"
            />
          )}
          <span className="text-xs text-default-400">
            {streamState === "streaming"
              ? "Streaming…"
              : isBusy
                ? "Working…"
                : statusText}
          </span>
        </div>
        <button
          type="button"
          aria-label={
            settingsOpen ? "Close session settings" : "Open session settings"
          }
          className="rounded px-2.5 py-1 text-xs text-default-500 transition-colors hover:bg-default-100 hover:text-foreground"
          onClick={onOpenSettings}
        >
          {settingsOpen ? "Close settings" : "Settings"}
        </button>
      </div>

      {/* Error banner */}
      {errorText && (
        <div
          role="alert"
          className="mx-4 mt-3 shrink-0 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger"
        >
          {errorText}
        </div>
      )}

      {/* Scrollable chat area — messages anchored to bottom */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="flex min-h-full flex-col">
          {/* Spacer pushes messages to the bottom when content is short */}
          <div className="flex-1" />
          <div className="mx-auto w-full max-w-3xl px-4 py-6">
            {!selectedSession ? (
              <Empty message="Select or create a session to start." />
            ) : jobs.length === 0 ? (
              <Empty message="No messages yet. Type a prompt below." />
            ) : (
              jobs.map((job) => (
                <JobThread
                  key={job.id}
                  job={job}
                  isStreaming={job.id === streamingJobId}
                />
              ))
            )}
            <div ref={bottomRef} />
          </div>
        </div>
      </div>
    </div>
  );
}
