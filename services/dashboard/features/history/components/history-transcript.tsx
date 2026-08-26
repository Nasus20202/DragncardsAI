"use client";

import { Chip, Spinner } from "@heroui/react";
import {
  Fragment,
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  HistoryEvent,
  JsonValue,
  RestoreMode,
  RestoreOutcome,
} from "@/features/shared/lib/types";
import { ConversationTranscript } from "@/features/history/components/conversation-transcript";
import { RestoreControl } from "@/features/history/components/restore-control";
import { BoardOpenControl } from "@/features/history/components/board-control";
import { ScoreChip } from "@/features/history/components/score-chip";
import { useEventDetail } from "@/features/history/lib/use-event-detail";
import {
  TranscriptWindow,
  extendNewer,
  extendOlder,
  isAtNewest,
  isAtOldest,
  refitWindow,
  tailWindow,
  windowContaining,
} from "@/features/history/lib/transcript-window";
import {
  actionLabel,
  buildHeadingBySeq,
  buildMetaBySeq,
  buildRoundEndBySeq,
  evaluatorModel,
  eventSearchText,
  formatScore,
  groupEvalsByTarget,
  phaseName,
  primaryEvents,
  verdictLevel,
  verdictPlayer,
  verdictScopeLabel,
} from "@/features/history/lib/history-rounds";

/**
 * A global expand/collapse pulse: bumping `generation` forces every event body
 * to `expanded`, overriding per-event toggles, while still letting per-event
 * toggles take over afterwards.
 */
export interface ExpandSignal {
  generation: number;
  expanded: boolean;
}

/**
 * A reveal pulse: when `seq` matches an event, that event opens its body
 * (`mode: "body"`, e.g. from a nav-tree click) or its evaluation sub-tree and
 * scrolls to it (`mode: "evals"`). Bumping `nonce` re-fires the reveal.
 */
export interface RevealSignal {
  seq: number | null;
  mode: "body" | "evals";
  nonce: number;
}

/**
 * Shared empty verdict list. A fresh `[]` per event would change a prop on every
 * ungraded event on every render, defeating `TranscriptEvent`'s memoisation.
 */
const NO_VERDICTS: HistoryEvent[] = [];

/**
 * Default pulses, hoisted out of the parameter list: inline default literals are
 * rebuilt on every render, which would change a prop on every memoised event row
 * for callers that omit them.
 */
const NO_EXPAND_SIGNAL: ExpandSignal = { generation: 0, expanded: false };
const NO_REVEAL: RevealSignal = { seq: null, mode: "body", nonce: 0 };

function hhmmss(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function stringifyValue(value: JsonValue | undefined | null): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function Field({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-semibold uppercase tracking-wide text-default-400">
        {label}
      </span>
      <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-lg border border-default-200/60 bg-default-50/40 px-3 py-2 text-xs leading-relaxed text-default-600 dark:bg-white/3 dark:text-default-300">
        {value}
      </pre>
    </div>
  );
}

/**
 * A field whose (typically JSON) value is collapsed by default behind a toggle,
 * so large blobs (action arguments, full game state) don't make the transcript
 * unreadable. Expands on demand.
 */
function CollapsibleField({
  label,
  value,
  testId,
}: {
  label: string;
  value: string;
  testId?: string;
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const preRef = useRef<HTMLPreElement>(null);
  if (!value) return null;

  const stop = (e: { stopPropagation: () => void }) => e.stopPropagation();
  const scrollPreTo = (top: number) =>
    preRef.current?.scrollTo({ top, behavior: "smooth" });
  const copy = () => {
    void navigator.clipboard?.writeText(value).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    });
  };

  const toolbarBtn =
    "rounded px-1.5 py-0.5 text-xs text-default-400 transition-colors hover:bg-default-100 hover:text-foreground";

  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        data-testid={testId}
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((p) => !p);
        }}
        className="flex items-center gap-1.5 self-start py-1 text-xs font-semibold uppercase tracking-wide text-default-400 transition-colors hover:text-foreground"
      >
        <span aria-hidden="true">{open ? "▾" : "▸"}</span>
        {label}
      </button>
      {open && (
        <div className="overflow-hidden rounded-lg border border-default-200/60">
          <div className="flex items-center gap-0.5 border-b border-default-200/60 bg-default-100/70 px-1.5 py-1 dark:bg-white/5">
            <button
              type="button"
              data-testid={testId ? `${testId}-copy` : undefined}
              onClick={(e) => {
                stop(e);
                copy();
              }}
              className={toolbarBtn}
            >
              {copied ? "✓ Copied" : "⧉ Copy"}
            </button>
            <span
              aria-hidden="true"
              className="mx-0.5 h-3.5 w-px bg-default-300/60"
            />
            <button
              type="button"
              data-testid={testId ? `${testId}-top` : undefined}
              onClick={(e) => {
                stop(e);
                scrollPreTo(0);
              }}
              className={toolbarBtn}
            >
              ↑ Top
            </button>
            <button
              type="button"
              data-testid={testId ? `${testId}-bottom` : undefined}
              onClick={(e) => {
                stop(e);
                scrollPreTo(preRef.current?.scrollHeight ?? 0);
              }}
              className={toolbarBtn}
            >
              ↓ Bottom
            </button>
          </div>
          <pre
            ref={preRef}
            onClick={stop}
            className="max-h-96 overflow-auto whitespace-pre bg-default-50/40 px-3 py-2 font-mono text-xs leading-relaxed text-default-600 dark:bg-white/3 dark:text-default-300"
          >
            {value}
          </pre>
        </div>
      )}
    </div>
  );
}

/* ── Per-actor inline bodies ─────────────────────────────────────── */

function AgentBody({ event }: { event: HistoryEvent }) {
  const intended = event.payload.intended_action;
  const reasoning = event.payload.reasoning;
  const args = event.payload.arguments;
  const context = event.payload.conversation_context;
  // The conversation is the bulk of an agent move and makes the transcript
  // unreadable when always expanded — collapse it per event (closed by default).
  const [showConversation, setShowConversation] = useState(false);
  const convoRef = useRef<HTMLDivElement>(null);
  const scrollConvoTo = (top: number) =>
    convoRef.current?.scrollTo({ top, behavior: "smooth" });
  const messageCount = Array.isArray(context) ? context.length : 0;
  const hasConversation = messageCount > 0;

  return (
    <div className="flex flex-col gap-3" data-testid="history-detail-agent">
      <Field
        label="Intended action"
        value={
          typeof intended === "string" ? intended : stringifyValue(intended)
        }
      />
      <Field
        label="Reasoning"
        value={
          typeof reasoning === "string" ? reasoning : stringifyValue(reasoning)
        }
      />
      <CollapsibleField
        label="Arguments"
        value={stringifyValue(args)}
        testId={`history-arguments-toggle-${event.seq}`}
      />
      {hasConversation && (
        <div className="flex flex-col gap-2">
          <button
            type="button"
            data-testid={`history-conversation-toggle-${event.seq}`}
            aria-expanded={showConversation}
            onClick={(e) => {
              e.stopPropagation();
              setShowConversation((p) => !p);
            }}
            className="flex items-center gap-1.5 self-start py-1 text-xs font-semibold uppercase tracking-wide text-default-400 transition-colors hover:text-foreground hover:underline"
          >
            <span aria-hidden="true">{showConversation ? "▾" : "▸"}</span>
            Conversation
            <span className="font-normal lowercase tracking-normal text-default-400">
              ({messageCount} message{messageCount === 1 ? "" : "s"})
            </span>
          </button>
          {showConversation && (
            <div
              className="overflow-hidden rounded-lg border border-default-200/60"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center gap-0.5 border-b border-default-200/60 bg-default-100/70 px-1.5 py-1 dark:bg-white/5">
                <button
                  type="button"
                  data-testid={`history-conversation-top-${event.seq}`}
                  onClick={() => scrollConvoTo(0)}
                  className="rounded px-1.5 py-0.5 text-xs text-default-400 transition-colors hover:bg-default-100 hover:text-foreground"
                >
                  ↑ Top
                </button>
                <button
                  type="button"
                  data-testid={`history-conversation-bottom-${event.seq}`}
                  onClick={() =>
                    scrollConvoTo(convoRef.current?.scrollHeight ?? 0)
                  }
                  className="rounded px-1.5 py-0.5 text-xs text-default-400 transition-colors hover:bg-default-100 hover:text-foreground"
                >
                  ↓ Bottom
                </button>
              </div>
              <div
                ref={convoRef}
                data-testid={`history-conversation-${event.seq}`}
                className="max-h-96 overflow-y-auto bg-default-50/40 p-3 dark:bg-white/3"
              >
                <ConversationTranscript context={context} />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function GameBody({ event }: { event: HistoryEvent }) {
  const status = event.payload.status;
  const state = event.payload.state;
  return (
    <div className="flex flex-col gap-3" data-testid="history-detail-game">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-default-400">
          Game status
        </span>
        <Chip size="sm" variant="soft" color="accent">
          {typeof status === "string" && status.length > 0 ? status : "unknown"}
        </Chip>
      </div>
      <CollapsibleField
        label="State"
        value={stringifyValue(state)}
        testId={`history-state-toggle-${event.seq}`}
      />
    </div>
  );
}

function UserBody({ event }: { event: HistoryEvent }) {
  const prompt = event.payload.prompt;
  const text = typeof prompt === "string" ? prompt : stringifyValue(prompt);
  return (
    <div className="flex justify-end" data-testid="history-detail-user">
      <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-tr-sm bg-default-100 px-4 py-2.5 text-sm leading-relaxed text-foreground dark:bg-white/6">
        {text || "User prompt"}
      </div>
    </div>
  );
}

/* ── Nested verdict sub-tree ─────────────────────────────────────── */

function VerdictSubtree({
  graded,
  verdicts,
  selectedSeq,
  onSelect,
  open,
  onToggle,
}: {
  graded: HistoryEvent;
  verdicts: HistoryEvent[];
  selectedSeq: number | null;
  onSelect: (seq: number) => void;
  open: boolean;
  onToggle: () => void;
}) {
  // Which verdicts have their full detail (all scores, rationale, flags)
  // expanded — the sub-tree row toggles its own details open.
  const [openVerdicts, setOpenVerdicts] = useState<Set<number>>(new Set());
  const toggleVerdict = (seq: number) =>
    setOpenVerdicts((current) => {
      const next = new Set(current);
      if (next.has(seq)) next.delete(seq);
      else next.add(seq);
      return next;
    });

  // Order per-move verdicts before per-player round/game roll-ups so the higher
  // levels read as a distinct summary band beneath the moves, while keeping the
  // original order within a level (stable sort).
  const levelRank = { move: 0, round: 1, game: 2 } as const;
  const orderedVerdicts = useMemo(
    () =>
      [...verdicts].sort(
        (a, b) => levelRank[verdictLevel(a)] - levelRank[verdictLevel(b)]
      ),
    // levelRank is a stable literal; verdicts is the only real dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [verdicts]
  );

  return (
    <div className="ml-3 mt-2 border-l border-default-200/60 pl-3">
      <button
        type="button"
        data-testid={`history-evals-toggle-${graded.seq}`}
        aria-expanded={open}
        onClick={onToggle}
        className="flex items-center gap-1.5 py-1 text-xs font-medium text-success hover:underline"
      >
        <span aria-hidden="true">{open ? "▾" : "▸"}</span>
        {verdicts.length} evaluation{verdicts.length > 1 ? "s" : ""}
      </button>

      {open && (
        <ul
          className="flex flex-col gap-1 pb-1"
          data-testid={`history-evals-${graded.seq}`}
        >
          {orderedVerdicts.map((verdict) => {
            const model = evaluatorModel(verdict);
            const scopeLabel = verdictScopeLabel(verdict);
            const level = verdictLevel(verdict);
            const player = verdictPlayer(verdict);
            // Per-player round/game roll-ups read as a distinct band from the
            // per-move verdicts: a stronger tint and a level marker on the row.
            const isRollup = level !== "move";
            const rationale =
              typeof verdict.payload.rationale === "string"
                ? verdict.payload.rationale
                : null;
            const vOpen = openVerdicts.has(verdict.seq);
            const scoresVal = verdict.payload.scores;
            const scoreEntries =
              scoresVal &&
              typeof scoresVal === "object" &&
              !Array.isArray(scoresVal)
                ? Object.entries(scoresVal as Record<string, JsonValue>)
                : [];
            const flags = Array.isArray(verdict.payload.flags)
              ? (verdict.payload.flags as JsonValue[])
              : [];
            const evVal = verdict.payload.evaluator;
            const evRec =
              evVal && typeof evVal === "object" && !Array.isArray(evVal)
                ? (evVal as Record<string, JsonValue>)
                : null;
            const version =
              typeof evRec?.evaluator_version === "string"
                ? evRec.evaluator_version
                : null;
            return (
              <li key={verdict.event_id ?? verdict.seq}>
                <button
                  type="button"
                  data-testid={`history-eval-${verdict.seq}`}
                  aria-current={
                    selectedSeq === verdict.seq ? "true" : undefined
                  }
                  aria-expanded={vOpen}
                  onClick={() => {
                    onSelect(verdict.seq);
                    toggleVerdict(verdict.seq);
                  }}
                  data-level={level}
                  className={[
                    "flex w-full flex-col gap-0.5 rounded-md border px-2 py-1.5 text-left transition-colors",
                    isRollup ? "ml-3" : "",
                    vOpen
                      ? "border-success/60 bg-success/10"
                      : isRollup
                        ? "border-success/40 bg-success/10 hover:bg-success/15"
                        : "border-success/30 bg-success/5 hover:bg-success/10",
                  ].join(" ")}
                >
                  <div className="flex items-center gap-1.5">
                    <span aria-hidden="true" className="text-xs text-success">
                      {vOpen ? "▾" : "▸"}
                    </span>
                    <Chip
                      size="sm"
                      variant="soft"
                      color="default"
                      data-testid={`history-eval-scope-${verdict.seq}`}
                    >
                      {scopeLabel}
                    </Chip>
                    {player && (
                      <Chip
                        size="sm"
                        variant="soft"
                        color="default"
                        className="bg-secondary/15 text-secondary"
                        data-testid={`history-eval-player-${verdict.seq}`}
                      >
                        {player}
                      </Chip>
                    )}
                    <ScoreChip
                      value={verdict.payload.overall_score}
                      testId={`history-eval-score-${verdict.seq}`}
                    />
                    {model && (
                      <span className="truncate text-xs text-default-400">
                        {model}
                      </span>
                    )}
                  </div>
                  {!vOpen && rationale && (
                    <span className="line-clamp-2 text-xs text-default-500">
                      {rationale}
                    </span>
                  )}
                </button>
                {vOpen && (
                  <div
                    data-testid={`history-eval-detail-${verdict.seq}`}
                    className="mt-1 flex flex-col gap-2 rounded-md border border-success/20 bg-success/5 px-2 py-2 text-xs"
                  >
                    {scoreEntries.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {scoreEntries.map(([k, v]) => (
                          <Chip
                            key={k}
                            size="sm"
                            variant="soft"
                            color="default"
                          >
                            {k.replace(/_/g, " ")}: {String(v)}
                          </Chip>
                        ))}
                      </div>
                    )}
                    {rationale && (
                      <p className="whitespace-pre-wrap leading-relaxed text-default-600 dark:text-default-300">
                        {rationale}
                      </p>
                    )}
                    {flags.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {flags.map((f, i) => (
                          <Chip
                            key={i}
                            size="sm"
                            variant="soft"
                            color="warning"
                          >
                            {String(f)}
                          </Chip>
                        ))}
                      </div>
                    )}
                    {(model || version) && (
                      <span className="text-default-400">
                        {model}
                        {version ? ` · ${version}` : ""}
                      </span>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/* ── One transcript event block ──────────────────────────────────── */

interface TranscriptEventProps {
  event: HistoryEvent;
  step: string | null;
  phase?: string | null;
  verdicts: HistoryEvent[];
  selected: boolean;
  /**
   * The current selection, but only when it is one of THIS event's verdicts —
   * the sub-tree is the only consumer. Passing the raw `selectedSeq` to every
   * event would change a prop on all of them whenever the selection moves,
   * defeating the memoisation below.
   */
  selectedVerdictSeq: number | null;
  onSelect: (seq: number) => void;
  // Inline per-event actions, only rendered on the focused event.
  onRestore: (targetSeq: number, mode: RestoreMode) => Promise<RestoreOutcome>;
  board: BoardActions;
  /**
   * DragnCards frontend base URL — environment config, not board state, which is
   * why it is its own prop rather than a field on `board`: the board bundle's
   * consumer never reads it (`BoardView` gets it directly from the workspace),
   * and only the restore control's "open the new game" link needs it.
   */
  frontendUrl?: string;
  platform?: "dragncards" | "marvel-lcg";
  // Global expand/collapse pulse — each event syncs its body to this on change.
  expandSignal: ExpandSignal;
  // Reveal pulse — open this event's body or evals when it is the target.
  reveal: RevealSignal;
}

/**
 * Memoised: a transcript of a played-out game runs to thousands of events, and
 * without this every one of them re-rendered on each selection change, search
 * keystroke and 15s poll refresh. All props are primitives or references the
 * parent keeps stable, so the default shallow comparison bails out on every
 * event the interaction did not actually touch.
 */
const TranscriptEvent = memo(function TranscriptEvent({
  event,
  step,
  phase,
  verdicts,
  selected,
  selectedVerdictSeq,
  onSelect,
  onRestore,
  board,
  frontendUrl,
  platform = "dragncards",
  expandSignal,
  reveal,
}: TranscriptEventProps) {
  const [showActions, setShowActions] = useState(false);
  const actionsRef = useRef<HTMLDivElement>(null);
  // The evaluation sub-tree open state lives here so the move's score chip can
  // open it (and scroll to it) on click, not just the sub-tree's own toggle.
  const [evalsOpen, setEvalsOpen] = useState(false);
  const evalsRef = useRef<HTMLDivElement>(null);
  const [scrollEvalsNonce, setScrollEvalsNonce] = useState(0);
  useEffect(() => {
    if (scrollEvalsNonce > 0) {
      evalsRef.current?.scrollIntoView({ block: "center" });
    }
  }, [scrollEvalsNonce]);
  const revealEvals = () => {
    setEvalsOpen(true);
    setScrollEvalsNonce((n) => n + 1);
  };
  // The event's detail body (AgentBody/GameBody) is collapsed by default so the
  // transcript stays scannable; the summary line and the short user prompt
  // bubble are always visible. A global Expand/Collapse all pulse syncs this
  // whenever its generation changes, while per-event toggles still work after.
  // Adjusting state from a prop change is done during render (the React-blessed
  // alternative to a setState-in-effect) by tracking the last-applied pulse in
  // state.
  const [bodyOpen, setBodyOpen] = useState(false);
  // The listed event is a timeline entry, whose payload omits the raw game state
  // and the agent conversation — which is exactly what the body shows. Fetch the
  // complete event once, and only once the body is actually open.
  const detail = useEventDetail(
    board.gameId,
    event.seq,
    bodyOpen && event.payload_complete === false,
    platform
  );
  const detailed = detail.event ?? event;
  const [lastSignalGen, setLastSignalGen] = useState(expandSignal.generation);
  if (lastSignalGen !== expandSignal.generation) {
    setLastSignalGen(expandSignal.generation);
    setBodyOpen(expandSignal.expanded);
  }
  // React to a reveal pulse targeting this event (nav click → body; score
  // chip / external → evals + scroll), tracking the last-applied nonce in state.
  const [lastRevealNonce, setLastRevealNonce] = useState(reveal.nonce);
  if (reveal.nonce !== lastRevealNonce) {
    setLastRevealNonce(reveal.nonce);
    if (reveal.seq === event.seq) {
      if (reveal.mode === "body") setBodyOpen(true);
      else revealEvals();
    }
  }
  // Close the actions dropdown when clicking outside it.
  useEffect(() => {
    if (!showActions) return;
    const onDocMouseDown = (e: MouseEvent) => {
      if (
        actionsRef.current &&
        !actionsRef.current.contains(e.target as Node)
      ) {
        setShowActions(false);
      }
    };
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, [showActions]);
  const isUser = event.actor === "user";
  const isAgent = event.actor === "agent";
  const actorLabel = isUser ? "User" : isAgent ? "Agent" : "Game";
  // The Chip color union does not include "secondary"; tint the user chip via
  // className so it reads distinctly from the agent/game chips.
  const actorColor = isUser ? "default" : isAgent ? "warning" : "accent";
  const actorChipClass = isUser ? "bg-secondary/15 text-secondary" : undefined;

  const latestVerdictScore =
    verdicts.length > 0
      ? verdicts[verdicts.length - 1].payload.overall_score
      : null;
  const latestScore = formatScore(latestVerdictScore);

  return (
    <div className="flex flex-col">
      <div
        role="button"
        tabIndex={0}
        data-testid={`history-event-${event.seq}`}
        data-actor={event.actor}
        aria-current={selected ? "true" : undefined}
        onClick={() => onSelect(event.seq)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onSelect(event.seq);
          }
        }}
        className={[
          "flex flex-col gap-2 rounded-xl border px-4 py-3 text-left transition-colors",
          selected
            ? "border-primary/60 bg-primary/10"
            : "border-default-200/60 bg-default-50/40 hover:bg-default-100/60 dark:bg-white/3",
        ].join(" ")}
      >
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-semibold text-default-500">
            #{event.seq}
          </span>
          <Chip
            size="sm"
            variant="soft"
            color={actorColor}
            className={actorChipClass}
          >
            {actorLabel}
          </Chip>
          {step && (
            <Chip
              size="sm"
              variant="soft"
              color="default"
              data-testid={`history-event-phase-${event.seq}`}
            >
              {phase ?? (platform === "dragncards" ? phaseName(step) : null)}
              {platform === "dragncards" && step ? ` ${step}` : ""}
            </Chip>
          )}
          {latestScore && (
            <button
              type="button"
              data-testid={`history-event-eval-indicator-${event.seq}`}
              title="View evaluation"
              onClick={(e) => {
                e.stopPropagation();
                onSelect(event.seq);
                revealEvals();
              }}
              className="rounded-full"
            >
              <ScoreChip value={latestVerdictScore} />
            </button>
          )}
          <span className="ml-auto text-xs text-default-400">
            {hhmmss(event.occurred_at)}
          </span>
          <div className="relative" ref={actionsRef}>
            <button
              type="button"
              data-testid={`history-event-actions-toggle-${event.seq}`}
              aria-expanded={showActions}
              aria-haspopup="menu"
              onClick={(e) => {
                e.stopPropagation();
                onSelect(event.seq);
                setShowActions((p) => !p);
              }}
              className="rounded-md border border-default-200/60 px-2 py-0.5 text-xs text-default-500 transition-colors hover:bg-default-100 hover:text-foreground"
            >
              Actions {showActions ? "▾" : "▸"}
            </button>
            {showActions && (
              <div
                role="menu"
                data-testid={`history-event-actions-${event.seq}`}
                onClick={(e) => e.stopPropagation()}
                className="absolute right-0 top-full z-30 mt-1 flex w-80 flex-col gap-2 rounded-xl border border-default-200/60 bg-background p-2 shadow-xl"
              >
                {/*
                  Read-only first, destructive last. All three actions used to sit
                  in one undifferentiated list, so the cheapest and safest thing a
                  user usually wants -- just looking at the board -- was below two
                  controls that change a game.
                */}
                <BoardOpenControl
                  gameId={board.gameId}
                  selectedSeq={event.seq}
                  isOpening={board.isOpening}
                  error={board.error}
                  isOpen={board.isOpen}
                  onOpen={board.onOpen}
                  platform={platform}
                />
                <RestoreControl
                  targetSeq={event.seq}
                  onRestore={onRestore}
                  frontendUrl={frontendUrl}
                  platform={platform}
                />
              </div>
            )}
          </div>
        </div>

        {isUser ? (
          <span className="text-sm font-medium text-foreground">
            {actionLabel(event)}
          </span>
        ) : (
          <button
            type="button"
            data-testid={`history-event-body-toggle-${event.seq}`}
            aria-expanded={bodyOpen}
            onClick={(e) => {
              e.stopPropagation();
              onSelect(event.seq);
              setBodyOpen((p) => !p);
            }}
            className="flex items-center gap-1.5 self-start text-left text-sm font-medium text-foreground transition-colors hover:text-primary hover:underline"
          >
            <span aria-hidden="true" className="text-xs text-default-400">
              {bodyOpen ? "▾" : "▸"}
            </span>
            {actionLabel(event)}
          </button>
        )}

        {isUser ? (
          <UserBody event={event} />
        ) : bodyOpen && detail.isLoading ? (
          <div
            data-testid={`history-detail-loading-${event.seq}`}
            className="flex items-center gap-2 text-xs text-default-400"
          >
            <Spinner size="sm" />
            Loading event…
          </div>
        ) : bodyOpen && detail.error ? (
          <div
            data-testid={`history-detail-error-${event.seq}`}
            role="alert"
            className="text-xs text-danger"
          >
            {detail.error}
          </div>
        ) : bodyOpen && isAgent ? (
          <AgentBody event={detailed} />
        ) : bodyOpen ? (
          <GameBody event={detailed} />
        ) : null}
      </div>

      {verdicts.length > 0 && (
        <div ref={evalsRef}>
          <VerdictSubtree
            graded={event}
            verdicts={verdicts}
            selectedSeq={selectedVerdictSeq}
            onSelect={onSelect}
            open={evalsOpen}
            onToggle={() => setEvalsOpen((p) => !p)}
          />
        </div>
      )}
    </div>
  );
});

/* ── Main transcript ─────────────────────────────────────────────── */

export interface BoardActions {
  gameId: string | null;
  isOpening: boolean;
  error: string | null;
  isOpen: boolean;
  onOpen: () => void;
}

export interface HistoryTranscriptProps {
  events: HistoryEvent[];
  selectedSeq: number | null;
  onSelect: (seq: number) => void;
  onRestore: (targetSeq: number, mode: RestoreMode) => Promise<RestoreOutcome>;
  board: BoardActions;
  /** DragnCards frontend base URL, for the restore control's new-game link. */
  frontendUrl?: string;
  platform?: "dragncards" | "marvel-lcg";
  // Global expand/collapse pulse from the workspace toolbar (default: collapsed).
  expandSignal?: ExpandSignal;
  // Case-insensitive transcript search query (empty string = no filter).
  searchQuery?: string;
  // Reveal pulse (nav-tree click → open the target event's body).
  reveal?: RevealSignal;
}

export function HistoryTranscript({
  events,
  selectedSeq,
  onSelect,
  onRestore,
  board,
  frontendUrl,
  platform = "dragncards",
  expandSignal = NO_EXPAND_SIGNAL,
  searchQuery = "",
  reveal = NO_REVEAL,
}: HistoryTranscriptProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  // Per-seq map of event elements, so a navigation-tree selection can scroll
  // the chosen event into view (see the selectedSeq effect below).
  const eventRefs = useRef(new Map<number, HTMLDivElement>());
  // Guards the scroll-into-view so it fires only on an explicit selection
  // change — never re-firing on re-render and never fighting the auto-follow.
  const lastScrolledSeqRef = useRef<number | null>(null);
  // VSCode-style scroll lock: auto-scroll only while parked near the bottom.
  // Scrolling up unlocks it; "Jump to latest" re-locks it.
  const [isLocked, setIsLocked] = useState(true);
  const suppressScrollUntilRef = useRef(0);
  // Tracks the last-seen event count so auto-follow fires only when new events
  // are appended during live play — not on the initial load, a same-length poll
  // refresh, or a local field toggle (which must never move the scroll).
  const prevCountRef = useRef(events.length);

  const NEAR_BOTTOM_THRESHOLD_PX = 80;
  const PROGRAMMATIC_SCROLL_GUARD_MS = 600;

  const allPrimary = useMemo(() => primaryEvents(events), [events]);
  const evalsByTarget = useMemo(() => groupEvalsByTarget(events), [events]);
  const metaBySeq = useMemo(() => buildMetaBySeq(events), [events]);

  // Search filters the visible primary events; headings and round-end markers
  // are then derived from the FILTERED list so a round only shows its
  // boundaries when it still has a matching event.
  const query = searchQuery.trim().toLowerCase();
  const primary = useMemo(() => {
    if (!query) return allPrimary;
    return allPrimary.filter((event) => eventSearchText(event).includes(query));
  }, [allPrimary, query]);

  const headingBySeq = useMemo(
    () => buildHeadingBySeq(primary, metaBySeq),
    [primary, metaBySeq]
  );
  const roundEndBySeq = useMemo(
    () => buildRoundEndBySeq(primary, metaBySeq),
    [primary, metaBySeq]
  );

  /* ── Endless scroll ──────────────────────────────────────────────
     Only a window of `primary` is rendered, opening at the newest end and
     growing when the reader reaches an edge. Both edges are watched by an
     IntersectionObserver on a sentinel, and the window is re-fitted (during
     render, tracking the last-applied length in state) whenever the list length
     changes under it — a search keystroke or an append from live play. */
  const indexOfSeq = (seq: number | null) =>
    seq == null ? -1 : primary.findIndex((event) => event.seq === seq);
  const [window_, setWindow] = useState<TranscriptWindow>(() => {
    // An initial selection (a deep link, or a game opened with a move already
    // picked) has to be inside the opening window or there is nothing to scroll.
    const opening = tailWindow(primary.length);
    const index = indexOfSeq(selectedSeq);
    return index < 0
      ? opening
      : windowContaining(opening, index, primary.length);
  });
  const [lastTotal, setLastTotal] = useState(primary.length);
  if (lastTotal !== primary.length) {
    setLastTotal(primary.length);
    setWindow((current) => refitWindow(current, lastTotal, primary.length));
  }
  // A selection outside the rendered window has to bring the window with it — a
  // round jump, or a navigation-tree click into a distant round. Adjusted during
  // render (tracking the last-applied selection in state) rather than in an
  // effect, matching how this file already reacts to the expand and reveal
  // pulses; a setState inside an effect would cascade a second render.
  const [lastSelected, setLastSelected] = useState(selectedSeq);
  if (lastSelected !== selectedSeq) {
    setLastSelected(selectedSeq);
    const index = indexOfSeq(selectedSeq);
    if (index >= 0) {
      setWindow((current) => windowContaining(current, index, primary.length));
    }
  }
  const visible = primary.slice(window_.start, window_.end);
  const hasOlder = !isAtOldest(window_);
  const hasNewer = !isAtNewest(window_, primary.length);
  const olderSentinelRef = useRef<HTMLDivElement>(null);
  const newerSentinelRef = useRef<HTMLDivElement>(null);
  const showOlder = useCallback(() => setWindow(extendOlder), []);
  const showNewer = useCallback(
    () => setWindow((current) => extendNewer(current, primary.length)),
    [primary.length]
  );

  useEffect(() => {
    const older = olderSentinelRef.current;
    const newer = newerSentinelRef.current;
    const root = scrollRef.current;
    if (!root || (!older && !newer)) return;
    // `IntersectionObserver` is absent in jsdom and in older browsers; the
    // explicit sentinel buttons remain the accessible fallback either way.
    if (typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          if (entry.target === older) showOlder();
          else showNewer();
        }
      },
      { root, rootMargin: "200px" }
    );
    if (older) observer.observe(older);
    if (newer) observer.observe(newer);
    return () => observer.disconnect();
  }, [showOlder, showNewer, hasOlder, hasNewer]);

  const isNearBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return true;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    return distanceFromBottom <= NEAR_BOTTOM_THRESHOLD_PX;
  }, []);

  const scrollToBottom = useCallback(() => {
    suppressScrollUntilRef.current = Date.now() + PROGRAMMATIC_SCROLL_GUARD_MS;
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, []);

  const handleScroll = useCallback(() => {
    if (Date.now() < suppressScrollUntilRef.current) return;
    setIsLocked(isNearBottom());
  }, [isNearBottom]);

  const jumpToLatest = useCallback(() => {
    setIsLocked(true);
    // The newest events may be outside the rendered window after a round jump,
    // so returning to "latest" has to move the window, not just the scrollbar.
    setWindow((current) =>
      tailWindow(primary.length, Math.max(current.end - current.start, 1))
    );
    scrollToBottom();
  }, [primary.length, scrollToBottom]);

  useEffect(() => {
    const prev = prevCountRef.current;
    prevCountRef.current = events.length;
    // Only auto-follow when events were appended after an initial non-empty
    // load; never on first population, poll refreshes, or field toggles.
    if (isLocked && prev > 0 && events.length > prev) {
      scrollToBottom();
    }
  }, [events, isLocked, scrollToBottom]);

  // Scroll the selected event into view on an explicit selection change (e.g. a
  // navigation-tree click). Guarded so it only fires when the selection truly
  // changes, never re-running on re-render or fighting the auto-follow lock. It
  // also runs once the window has caught up, since the element may not have been
  // rendered when the selection first landed.
  useEffect(() => {
    if (selectedSeq == null) {
      lastScrolledSeqRef.current = null;
      return;
    }
    if (lastScrolledSeqRef.current === selectedSeq) return;
    const el = eventRefs.current.get(selectedSeq);
    if (!el) return;
    lastScrolledSeqRef.current = selectedSeq;
    suppressScrollUntilRef.current = Date.now() + PROGRAMMATIC_SCROLL_GUARD_MS;
    el.scrollIntoView({ block: "center" });
  }, [selectedSeq, window_]);

  if (events.length === 0) {
    return (
      <div
        data-testid="history-empty"
        className="flex h-full items-center justify-center px-4 text-center text-sm text-default-500"
      >
        No history recorded for this game yet.
      </div>
    );
  }

  return (
    <div className="relative min-h-0 flex-1">
      <div
        ref={scrollRef}
        className="h-full overflow-y-auto overflow-x-hidden"
        onScroll={handleScroll}
        data-testid="history-transcript"
      >
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-2 px-4 py-4">
          {query && primary.length === 0 && (
            <div
              data-testid="history-search-empty"
              className="flex items-center justify-center px-4 py-12 text-center text-sm text-default-500"
            >
              No events match “{searchQuery.trim()}”.
            </div>
          )}
          {hasOlder && (
            <div ref={olderSentinelRef} className="flex justify-center">
              <button
                type="button"
                data-testid="history-load-older"
                onClick={showOlder}
                className="rounded-full border border-default-200/60 px-3 py-1 text-xs text-default-500 transition-colors hover:bg-default-100 hover:text-foreground"
              >
                Show earlier events
              </button>
            </div>
          )}
          {visible.map((event) => {
            const meta = metaBySeq.get(event.seq) ?? {
              round: null,
              step: null,
              platform,
              phase: null,
            };
            const heading = headingBySeq.get(event.seq) ?? null;
            const roundEnd = roundEndBySeq.get(event.seq) ?? null;
            const verdicts = evalsByTarget.get(event.seq) ?? NO_VERDICTS;
            return (
              <Fragment key={event.event_id ?? event.seq}>
                {heading && (
                  <div
                    data-testid={`history-round-${heading.key}`}
                    className="sticky top-0 z-10 -mx-4 bg-background/95 px-4 pb-1 pt-2 text-xs font-semibold uppercase tracking-wide text-default-500 backdrop-blur"
                  >
                    {heading.label}
                  </div>
                )}
                <div
                  ref={(el) => {
                    if (el) eventRefs.current.set(event.seq, el);
                    else eventRefs.current.delete(event.seq);
                  }}
                >
                  <TranscriptEvent
                    event={event}
                    step={meta.step}
                    phase={meta.phase}
                    platform={meta.platform ?? platform}
                    verdicts={verdicts}
                    selected={selectedSeq === event.seq}
                    selectedVerdictSeq={
                      verdicts.some((verdict) => verdict.seq === selectedSeq)
                        ? selectedSeq
                        : null
                    }
                    onSelect={onSelect}
                    onRestore={onRestore}
                    board={board}
                    frontendUrl={frontendUrl}
                    expandSignal={expandSignal}
                    reveal={reveal}
                  />
                </div>
                {roundEnd && (
                  <div
                    data-testid={`history-round-end-${roundEnd.key}`}
                    className="-mx-4 px-4 pb-2 pt-1 text-xs font-semibold uppercase tracking-wide text-default-400"
                  >
                    {roundEnd.label}
                  </div>
                )}
              </Fragment>
            );
          })}
          {hasNewer && (
            <div ref={newerSentinelRef} className="flex justify-center">
              <button
                type="button"
                data-testid="history-load-newer"
                onClick={showNewer}
                className="rounded-full border border-default-200/60 px-3 py-1 text-xs text-default-500 transition-colors hover:bg-default-100 hover:text-foreground"
              >
                Show later events
              </button>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Also offered while the window stops short of the newest event, which is
          where a round jump leaves it even though the scrollbar is at the end. */}
      {(!isLocked || hasNewer) && (
        <button
          data-testid="history-jump-to-latest"
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
  );
}
