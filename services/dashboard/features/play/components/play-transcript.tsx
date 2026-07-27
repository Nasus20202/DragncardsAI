import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { JobDetail, SessionDetail } from "@/features/shared/lib/types";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  aggregateEvents,
  AggEvent,
  eventBodyText,
} from "@/features/play/lib/play-session-events";
import { JobEventResponse } from "@/features/shared/lib/types";

const JOB_STATE_LABELS = {
  streaming: "Streaming…",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
  queued: "Queued",
  running: "Running",
  working: "Working…",
} as const;

type VisibleJobStateKey = keyof typeof JOB_STATE_LABELS | "idle";

/* ── Sub-renderers ───────────────────────────────────────────────── */

/**
 * Reasoning block — open while the job is streaming, auto-collapses once
 * a model_output event has arrived (meaning the response is ready).
 */
function ReasoningBlock({
  text,
  isStreaming,
  hasOutput,
  isLast,
}: {
  text: string;
  isStreaming: boolean;
  hasOutput: boolean;
  isLast: boolean;
}) {
  // Start collapsed if:
  //   - The job is already done (not streaming and has output), OR
  //   - This is not the last/active reasoning block (there are more events after it)
  const [open, setOpen] = useState(isLast && (!hasOutput || isStreaming));
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
            {eventBodyText(event)}
          </pre>
        </div>
      )}
    </div>
  );
}

export function AggEventRow({
  agg,
  isStreaming,
  hasOutput,
  isLast = false,
}: {
  agg: AggEvent;
  isStreaming: boolean;
  hasOutput: boolean;
  /** Whether this is the last event in the list — used to keep the active reasoning block open. */
  isLast?: boolean;
}) {
  switch (agg.kind) {
    case "reasoning":
      return (
        <ReasoningBlock
          text={agg.text}
          isStreaming={isStreaming}
          hasOutput={hasOutput}
          isLast={isLast}
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
    case "skill_loaded":
      return (
        <CollapsibleEventBlock
          label={`Skill loaded: ${typeof agg.event.payload.skill_name === "string" ? agg.event.payload.skill_name : ""}`}
          dotClass="bg-secondary"
          event={agg.event}
        />
      );
    case "subagent_started":
    case "subagent_completed":
    case "subagent_failed": {
      const labels: Record<string, string> = {
        subagent_started: "Subagent started",
        subagent_completed: "Subagent completed",
        subagent_failed: "Subagent failed",
      };
      const childId =
        typeof agg.event.payload.child_job_id === "string"
          ? agg.event.payload.child_job_id
          : "";
      return (
        <p className="text-xs text-default-400">
          {labels[agg.kind]}
          {childId ? `: ${childId.slice(0, 8)}…` : ""}
        </p>
      );
    }
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
  const isCompactionJob = job.prompt === "[COMPACTION]";
  const aggEvents = aggregateEvents(job.events, isCompactionJob);
  const isWaiting = job.events.length === 0;
  const hasOutput = aggEvents.some((e) => e.kind === "model_output");

  return (
    <div className="mb-8 space-y-3">
      {!isCompactionJob && (
        <div className="flex justify-end">
          <div className="max-w-[78%] rounded-2xl rounded-tr-sm bg-default-100 px-4 py-2.5 text-base leading-relaxed text-foreground dark:bg-white/6">
            {job.prompt}
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
              isLast={i === aggEvents.length - 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Empty state ─────────────────────────────────────────────────── */
function Empty({ message }: { message: string }) {
  return <p className="text-sm text-default-400">{message}</p>;
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
  const scrollRef = useRef<HTMLDivElement>(null);
  // VSCode-style scroll lock: auto-scroll only while the user is parked at (or
  // near) the bottom. Scrolling up unlocks it; "Jump to latest" re-locks it.
  const [isLocked, setIsLocked] = useState(true);
  // While a programmatic (auto-follow / jump) scroll is animating, the
  // intermediate scroll positions are far from the bottom and would otherwise
  // flip isLocked off mid-animation. Suppress onScroll handling until this
  // timestamp to keep the follow locked.
  const suppressScrollUntilRef = useRef(0);
  const latestJobStatus = jobs.at(-1)?.status ?? null;

  // Treat anything within this many pixels of the bottom as "at the bottom" to
  // tolerate sub-pixel rounding and smooth-scroll lag.
  const NEAR_BOTTOM_THRESHOLD_PX = 80;
  // Smooth scrolls fire no reliable "finished" event, so ignore onScroll for a
  // short window after starting one.
  const PROGRAMMATIC_SCROLL_GUARD_MS = 600;

  const isNearBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) {
      return true;
    }
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    return distanceFromBottom <= NEAR_BOTTOM_THRESHOLD_PX;
  }, []);

  const scrollToBottom = useCallback(() => {
    suppressScrollUntilRef.current = Date.now() + PROGRAMMATIC_SCROLL_GUARD_MS;
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, []);

  const handleScroll = useCallback(() => {
    // Ignore scroll events caused by a programmatic scroll so it cannot unlock
    // the follow mid-animation.
    if (Date.now() < suppressScrollUntilRef.current) {
      return;
    }
    setIsLocked(isNearBottom());
  }, [isNearBottom]);

  const jumpToLatest = useCallback(() => {
    setIsLocked(true);
    scrollToBottom();
  }, [scrollToBottom]);

  function getVisibleJobStateKey(): VisibleJobStateKey {
    if (streamState === "streaming") {
      return "streaming";
    }

    switch (latestJobStatus) {
      case "completed":
      case "failed":
      case "cancelled":
      case "queued":
      case "running":
        return latestJobStatus;
    }

    if (isBusy) {
      return "working";
    }

    return "idle";
  }

  const visibleJobStateKey = getVisibleJobStateKey();
  const visibleJobState =
    visibleJobStateKey === "idle"
      ? statusText
      : JOB_STATE_LABELS[visibleJobStateKey];

  useEffect(() => {
    if (!isLocked) {
      return;
    }
    scrollToBottom();
  }, [jobs, isLocked, scrollToBottom]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Status bar */}
      <div
        data-testid="play-status-banner"
        className="flex h-10 shrink-0 items-center justify-between border-b border-default-200/60 px-4"
      >
        <div className="flex items-center gap-2">
          {streamState === "streaming" && (
            <span
              aria-hidden="true"
              className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-success"
            />
          )}
          <span
            data-testid="play-job-state"
            data-state={visibleJobStateKey}
            className="text-xs text-default-400"
          >
            {visibleJobState}
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
      <div className="relative min-h-0 flex-1">
        <div
          ref={scrollRef}
          className="h-full overflow-y-auto"
          onScroll={handleScroll}
        >
          <div className="flex min-h-full flex-col">
            {/* Spacer pushes messages to the bottom when content is short */}
            {selectedSession && jobs.length > 0 && <div className="flex-1" />}
            <div
              className={`mx-auto w-full max-w-3xl px-4 py-6 ${!selectedSession || jobs.length === 0 ? "flex flex-1 items-center justify-center" : ""}`}
            >
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

        {/* Jump-to-latest control — shown only when scroll lock is released */}
        {!isLocked && selectedSession && jobs.length > 0 && (
          <button
            data-testid="jump-to-latest"
            type="button"
            aria-label="Jump to latest"
            className="absolute bottom-4 right-4 z-10 flex items-center gap-1.5 rounded-full border border-default-200/60 bg-background/90 px-3 py-1.5 text-xs font-medium text-default-600 shadow-lg backdrop-blur-sm transition-colors hover:bg-default-100 hover:text-foreground"
            onClick={jumpToLatest}
          >
            <span aria-hidden="true">↓</span>
            Jump to latest
          </button>
        )}
      </div>
    </div>
  );
}
