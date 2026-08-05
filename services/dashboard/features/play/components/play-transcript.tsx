import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { JobDetail, SessionDetail } from "@/features/shared/lib/types";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  aggregateEvents,
  AggEvent,
  deriveUserQuestionResolutions,
  eventBodyText,
  parseIllegalActionFindingEvent,
  parseSeatScopeViolationEvent,
  parseUserQuestionEvent,
  TERMINAL_JOB_STATUSES,
  UserQuestionResolution,
} from "@/features/play/lib/play-session-events";
import {
  ToolExchangeBlock,
  ToolExchangeProvider,
} from "@/features/play/components/tool-exchange-block";
import { UserQuestionCard } from "@/features/play/components/user-question-card";
import {
  JobEventResponse,
  UserQuestionAnswerRequest,
} from "@/features/shared/lib/types";

/** Answers a question the model asked through `ask_user`. */
export type AnswerQuestionHandler = (
  jobId: string,
  questionId: string,
  body: UserQuestionAnswerRequest
) => Promise<void>;

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

/** Keys that scroll the transcript upwards, i.e. away from the newest output. */
const UPWARD_SCROLL_KEYS = new Set(["ArrowUp", "PageUp", "Home"]);

/* ── Sub-renderers ───────────────────────────────────────────────── */

/*
 * Every block below is memoised, and that is what keeps a long transcript
 * usable. A streamed token replaces one event inside one job, but React would
 * otherwise re-render — and, for model output, re-parse the markdown of — every
 * block in the whole session on each token, so the cost of a single token grew
 * with the length of the history. All of these blocks take only primitives or a
 * `JobEventResponse` whose identity is preserved unless its payload actually
 * changed (see `upsertStreamEvent`), so the default shallow comparison bails out
 * on exactly the blocks that did not change.
 */

/**
 * Reasoning block — open while the job is streaming, auto-collapses once
 * a model_output event has arrived (meaning the response is ready).
 */
const ReasoningBlock = memo(function ReasoningBlock({
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
});

const CompactionBlock = memo(function CompactionBlock({
  text,
}: {
  text: string;
}) {
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
});

const ModelOutputBlock = memo(function ModelOutputBlock({
  text,
}: {
  text: string;
}) {
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
});

const CollapsibleEventBlock = memo(function CollapsibleEventBlock({
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
});

export function AggEventRow({
  agg,
  isStreaming,
  hasOutput,
  isLast = false,
  jobId,
  questionResolutions,
  isJobTerminal = false,
  onAnswerQuestion,
}: {
  agg: AggEvent;
  isStreaming: boolean;
  hasOutput: boolean;
  /** Whether this is the last event in the list — used to keep the active reasoning block open. */
  isLast?: boolean;
  /**
   * The job these events belong to. Optional because the read-only subagent
   * output view renders rows without an answering path.
   */
  jobId?: string;
  /** Per-question resolutions derived from the job's durable event list. */
  questionResolutions?: Map<string, UserQuestionResolution>;
  isJobTerminal?: boolean;
  onAnswerQuestion?: AnswerQuestionHandler;
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
    case "tool_exchange":
      return <ToolExchangeBlock call={agg.call} result={agg.result} />;
    case "compaction":
      return <CompactionBlock text={agg.text} />;
    case "compaction_failed":
      // Deliberately not the danger styling the `failure` row uses: the turn
      // this interrupted still ran. What the reader needs to know is that the
      // history was not summarised, not that something was lost.
      return (
        <div className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm">
          <span className="mr-1.5 font-semibold text-warning">
            Context compaction failed
          </span>
          <span className="text-default-500">
            {eventBodyText(agg.event)} — this turn continued on the history it
            already had.
          </span>
        </div>
      );
    case "turn_continued": {
      // A seam, not a failure: the answer above and the answer below came from
      // two paid calls, and the reader is entitled to know that rather than
      // read them as one uninterrupted response.
      const payload = agg.event.payload as Record<string, unknown>;
      const finishReason =
        typeof payload.finish_reason === "string"
          ? payload.finish_reason
          : null;
      const attempt =
        typeof payload.continuation === "number" ? payload.continuation : null;
      const maxAttempts =
        typeof payload.max_continuations === "number"
          ? payload.max_continuations
          : null;
      const detail = [
        finishReason ? `provider reported "${finishReason}"` : null,
        attempt && maxAttempts
          ? `continuation ${attempt} of ${maxAttempts}`
          : null,
      ]
        .filter(Boolean)
        .join(", ");
      return (
        <div
          className="flex items-center gap-2 py-1 text-xs text-default-500"
          data-testid="play-turn-continued"
        >
          <span className="h-px flex-1 bg-default-200" aria-hidden="true" />
          <span className="shrink-0">
            Output limit reached — turn continued automatically
            {detail ? ` (${detail})` : ""}
          </span>
          <span className="h-px flex-1 bg-default-200" aria-hidden="true" />
        </div>
      );
    }
    case "skill_loaded":
      return (
        <CollapsibleEventBlock
          label={`Skill loaded: ${typeof agg.event.payload.skill_name === "string" ? agg.event.payload.skill_name : ""}`}
          dotClass="bg-secondary"
          event={agg.event}
        />
      );
    case "user_question": {
      const prompt = parseUserQuestionEvent(agg.event);
      if (!prompt) {
        // Unusable payload: fall back to the generic block rather than
        // rendering a question nobody can answer.
        return (
          <CollapsibleEventBlock
            label="Question for you"
            dotClass="bg-primary/60"
            event={agg.event}
          />
        );
      }
      return (
        <UserQuestionCard
          question={prompt}
          resolution={
            questionResolutions?.get(prompt.questionId) ?? { status: "pending" }
          }
          isJobTerminal={isJobTerminal}
          onAnswer={
            jobId && onAnswerQuestion
              ? (questionId, body) => onAnswerQuestion(jobId, questionId, body)
              : undefined
          }
        />
      );
    }
    case "seat_scope_violation": {
      const violation = parseSeatScopeViolationEvent(agg.event);
      if (!violation) {
        return (
          <CollapsibleEventBlock
            label="Seat boundary refusal"
            dotClass="bg-warning/60"
            event={agg.event}
          />
        );
      }
      // Warning styling, for the same reason `compaction_failed` uses it and the
      // `failure` row does not: nothing here is broken. The call never reached
      // the tool, which is the boundary doing its job.
      return (
        <div
          data-testid="seat-scope-violation"
          className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm"
        >
          <span className="mr-1.5 font-semibold text-warning">
            Refused: seat boundary held
          </span>
          <span className="text-default-500">
            {violation.playerId} named {violation.foreignPlayerId} in{" "}
            {violation.argument || "an argument"}
            {violation.value ? ` (${violation.value})` : ""}, so{" "}
            {violation.toolName || "the tool"} was not called.
          </span>
        </div>
      );
    }
    case "illegal_action_finding": {
      const finding = parseIllegalActionFindingEvent(agg.event);
      if (!finding) {
        return (
          <CollapsibleEventBlock
            label="Illegal action finding"
            dotClass="bg-danger/60"
            event={agg.event}
          />
        );
      }
      const isOpen = finding.status === "open";
      return (
        <div
          data-testid="illegal-action-finding"
          data-status={finding.status}
          className={`rounded-lg border px-3 py-2 text-sm ${isOpen ? "border-danger/30 bg-danger/10" : "border-default-200/60 bg-default-50/40 dark:bg-white/3"}`}
        >
          <span
            className={`mr-1.5 font-semibold ${isOpen ? "text-danger" : "text-default-500"}`}
          >
            {isOpen ? "Open finding" : "Resolved finding"}
          </span>
          <span className="text-default-500">
            {finding.playerId}
            {finding.roundNumber === null
              ? ""
              : `, round ${finding.roundNumber}`}
            : {finding.violation || "no violation recorded"}
            {isOpen && finding.requiredUndo
              ? ` — to undo: ${finding.requiredUndo}`
              : ""}
            {!isOpen && finding.resolutionNote
              ? ` — ${finding.resolutionNote}`
              : ""}
          </span>
        </div>
      );
    }
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
/**
 * Memoised on the job: a streamed token replaces exactly one job in the list
 * (see `applyStreamEventToJob`), so every settled thread above it bails out
 * instead of re-aggregating and re-rendering its events.
 */
const JobThread = memo(function JobThread({
  job,
  isStreaming,
  onAnswerQuestion,
}: {
  job: JobDetail;
  isStreaming: boolean;
  onAnswerQuestion?: AnswerQuestionHandler;
}) {
  const isCompactionJob = job.prompt === "[COMPACTION]";
  const aggEvents = useMemo(
    () => aggregateEvents(job.events, isCompactionJob),
    [job.events, isCompactionJob]
  );
  // Keyed off the same events array as the aggregation, so a settled thread
  // recomputes neither.
  const questionResolutions = useMemo(
    () => deriveUserQuestionResolutions(job.events),
    [job.events]
  );
  const isJobTerminal = TERMINAL_JOB_STATUSES.has(job.status);
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
              jobId={job.id}
              questionResolutions={questionResolutions}
              isJobTerminal={isJobTerminal}
              onAnswerQuestion={onAnswerQuestion}
            />
          ))}
        </div>
      )}
    </div>
  );
});

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
  onViewSubagent,
  onAnswerQuestion,
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
  /**
   * Open the subagent output view on a child job, offered by the cards for the
   * subagent tools. MUST be referentially stable — the transcript's blocks are
   * memoised and this value reaches them through context.
   */
  onViewSubagent?: (childJobId: string, name: string) => void;
  /**
   * Answers a model question. Optional so a transcript can be rendered without
   * an answering path; questions then show as pending but read-only.
   */
  onAnswerQuestion?: AnswerQuestionHandler;
  settingsOpen: boolean;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  // VSCode-style scroll lock: incoming output is followed only while the lock is
  // engaged. Any user-initiated upward scroll releases it so streaming tokens
  // stop yanking the viewport; reaching the bottom again — or pressing the
  // follow control — re-engages it.
  const [isLocked, setIsLocked] = useState(true);
  // While a programmatic (auto-follow / jump) scroll is animating, the
  // intermediate scroll positions are far from the bottom and would otherwise
  // flip isLocked off mid-animation. Suppress onScroll handling until this
  // timestamp to keep the follow locked.
  const suppressScrollUntilRef = useRef(0);
  const touchStartYRef = useRef<number | null>(null);
  const latestJobStatus = jobs.at(-1)?.status ?? null;

  // Tolerance for "the viewport is at the bottom", covering sub-pixel rounding
  // of fractional scroll heights only — a deliberate scroll away from the
  // bottom must always release the lock.
  const AT_BOTTOM_EPSILON_PX = 8;
  // Smooth scrolls fire no reliable "finished" event, so ignore onScroll for a
  // short window after starting one.
  const PROGRAMMATIC_SCROLL_GUARD_MS = 600;
  // Ignore incidental finger jitter before treating a touch drag as a scroll.
  const TOUCH_DRAG_THRESHOLD_PX = 8;

  const isAtBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) {
      return true;
    }
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    return distanceFromBottom <= AT_BOTTOM_EPSILON_PX;
  }, []);

  const scrollToBottom = useCallback(() => {
    suppressScrollUntilRef.current = Date.now() + PROGRAMMATIC_SCROLL_GUARD_MS;
    const el = scrollRef.current;
    // Scroll the container rather than the sentinel: `scrollIntoView` aligns the
    // sentinel's own box, which leaves the container's bottom padding below the
    // fold and reads back as "not at the bottom".
    if (el && typeof el.scrollTo === "function") {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
      return;
    }
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, []);

  /**
   * Release the follow lock in response to a user gesture. This must win even
   * mid-animation: during streaming the auto-follow re-arms the programmatic
   * scroll guard on every token, so a plain onScroll handler would never see the
   * user's scroll. Dropping the guard and pinning the container at its current
   * offset also cancels the in-flight smooth scroll, leaving the viewport where
   * the user put it.
   */
  const releaseFollow = useCallback(() => {
    suppressScrollUntilRef.current = 0;
    const el = scrollRef.current;
    if (el && typeof el.scrollTo === "function") {
      el.scrollTo({ top: el.scrollTop });
    }
    setIsLocked(false);
  }, []);

  const handleScroll = useCallback(() => {
    // Ignore scroll events caused by a programmatic scroll so it cannot unlock
    // the follow mid-animation.
    if (Date.now() < suppressScrollUntilRef.current) {
      return;
    }
    setIsLocked(isAtBottom());
  }, [isAtBottom]);

  const handleWheel = useCallback(
    (event: React.WheelEvent<HTMLDivElement>) => {
      if (event.deltaY < 0) {
        releaseFollow();
      }
    },
    [releaseFollow]
  );

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (UPWARD_SCROLL_KEYS.has(event.key)) {
        releaseFollow();
      }
    },
    [releaseFollow]
  );

  const handleTouchStart = useCallback(
    (event: React.TouchEvent<HTMLDivElement>) => {
      touchStartYRef.current = event.touches[0]?.clientY ?? null;
    },
    []
  );

  const handleTouchMove = useCallback(
    (event: React.TouchEvent<HTMLDivElement>) => {
      const startY = touchStartYRef.current;
      const currentY = event.touches[0]?.clientY;
      if (startY === null || currentY === undefined) {
        return;
      }
      // Dragging the finger downwards scrolls the content up, away from the
      // newest output.
      if (currentY - startY > TOUCH_DRAG_THRESHOLD_PX) {
        releaseFollow();
      }
    },
    [releaseFollow]
  );

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

  // The transcript resizes for reasons the job list does not capture: markdown
  // finishes laying out, and reasoning blocks auto-collapse once a response
  // lands. Watching the content box keeps both directions honest — while locked,
  // late growth is followed instead of leaving the viewport stranded short of the
  // bottom; while released, content shrinking back within one viewport re-engages
  // rather than stranding the follow control with nowhere to scroll to. A
  // `scroll` event cannot stand in here: browsers do not reliably fire one when
  // they clamp `scrollTop` for shrinking content.
  useEffect(() => {
    const content = contentRef.current;
    if (!content || typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver(() => {
      if (isLocked) {
        if (!isAtBottom()) {
          scrollToBottom();
        }
      } else if (isAtBottom()) {
        setIsLocked(true);
      }
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, [isAtBottom, isLocked, scrollToBottom]);

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
          onKeyDown={handleKeyDown}
          onScroll={handleScroll}
          onTouchMove={handleTouchMove}
          onTouchStart={handleTouchStart}
          onWheel={handleWheel}
        >
          <div ref={contentRef} className="flex min-h-full flex-col">
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
                <ToolExchangeProvider onViewSubagent={onViewSubagent}>
                  {jobs.map((job) => (
                    <JobThread
                      key={job.id}
                      job={job}
                      isStreaming={job.id === streamingJobId}
                      onAnswerQuestion={onAnswerQuestion}
                    />
                  ))}
                </ToolExchangeProvider>
              )}
              <div ref={bottomRef} />
            </div>
          </div>
        </div>

        {/* Follow control — shown only while the scroll lock is released, and
            doubles as the jump-to-latest affordance */}
        {!isLocked && selectedSession && jobs.length > 0 && (
          <button
            data-testid="jump-to-latest"
            type="button"
            aria-label="Resume following the latest output"
            title="Resume following the latest output"
            className="absolute bottom-4 right-4 z-10 flex items-center gap-1.5 rounded-full border border-default-200/60 bg-background/90 px-3 py-1.5 text-xs font-medium text-default-600 shadow-lg backdrop-blur-sm transition-colors hover:bg-default-100 hover:text-foreground"
            onClick={jumpToLatest}
          >
            <span aria-hidden="true">↓</span>
            Follow latest
          </button>
        )}
      </div>
    </div>
  );
}
