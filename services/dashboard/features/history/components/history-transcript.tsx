"use client";

import { Button, Card, Chip } from "@heroui/react";
import {
  Fragment,
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
    "h-auto rounded bg-transparent px-1.5 py-0.5 text-xs text-default-400 transition-colors hover:bg-default-100 hover:text-foreground";

  return (
    <div className="flex flex-col gap-1">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        data-testid={testId}
        aria-expanded={open}
        onPress={() => setOpen((p) => !p)}
        onClick={stop}
        className="flex h-auto items-center gap-1.5 self-start bg-transparent py-1 text-xs font-semibold uppercase tracking-wide text-default-400 transition-colors hover:text-foreground"
      >
        <span aria-hidden="true">{open ? "▾" : "▸"}</span>
        {label}
      </Button>
      {open && (
        <Card className="overflow-hidden p-0">
          <div className="flex items-center gap-0.5 border-b border-default-200/60 bg-default-100/70 px-1.5 py-1 dark:bg-white/5">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              data-testid={testId ? `${testId}-copy` : undefined}
              onPress={copy}
              onClick={stop}
              className={toolbarBtn}
            >
              {copied ? "✓ Copied" : "⧉ Copy"}
            </Button>
            <span
              aria-hidden="true"
              className="mx-0.5 h-3.5 w-px bg-default-300/60"
            />
            <Button
              type="button"
              variant="ghost"
              size="sm"
              data-testid={testId ? `${testId}-top` : undefined}
              onPress={() => scrollPreTo(0)}
              onClick={stop}
              className={toolbarBtn}
            >
              ↑ Top
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              data-testid={testId ? `${testId}-bottom` : undefined}
              onPress={() => scrollPreTo(preRef.current?.scrollHeight ?? 0)}
              onClick={stop}
              className={toolbarBtn}
            >
              ↓ Bottom
            </Button>
          </div>
          <pre
            ref={preRef}
            onClick={stop}
            className="max-h-96 overflow-auto whitespace-pre bg-default-50/40 px-3 py-2 font-mono text-xs leading-relaxed text-default-600 dark:bg-white/3 dark:text-default-300"
          >
            {value}
          </pre>
        </Card>
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
          <Button
            type="button"
            variant="ghost"
            size="sm"
            data-testid={`history-conversation-toggle-${event.seq}`}
            aria-expanded={showConversation}
            onPress={() => setShowConversation((p) => !p)}
            onClick={(e) => e.stopPropagation()}
            className="flex h-auto items-center gap-1.5 self-start bg-transparent py-1 text-xs font-semibold uppercase tracking-wide text-default-400 transition-colors hover:text-foreground hover:underline"
          >
            <span aria-hidden="true">{showConversation ? "▾" : "▸"}</span>
            Conversation
            <span className="font-normal lowercase tracking-normal text-default-400">
              ({messageCount} message{messageCount === 1 ? "" : "s"})
            </span>
          </Button>
          {showConversation && (
            <Card
              className="overflow-hidden p-0"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center gap-0.5 border-b border-default-200/60 bg-default-100/70 px-1.5 py-1 dark:bg-white/5">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  data-testid={`history-conversation-top-${event.seq}`}
                  onPress={() => scrollConvoTo(0)}
                  className="h-auto rounded bg-transparent px-1.5 py-0.5 text-xs text-default-400 transition-colors hover:bg-default-100 hover:text-foreground"
                >
                  ↑ Top
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  data-testid={`history-conversation-bottom-${event.seq}`}
                  onPress={() =>
                    scrollConvoTo(convoRef.current?.scrollHeight ?? 0)
                  }
                  className="h-auto rounded bg-transparent px-1.5 py-0.5 text-xs text-default-400 transition-colors hover:bg-default-100 hover:text-foreground"
                >
                  ↓ Bottom
                </Button>
              </div>
              <div
                ref={convoRef}
                data-testid={`history-conversation-${event.seq}`}
                className="max-h-96 overflow-y-auto bg-default-50/40 p-3 dark:bg-white/3"
              >
                <ConversationTranscript context={context} />
              </div>
            </Card>
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
      <Button
        type="button"
        variant="ghost"
        size="sm"
        data-testid={`history-evals-toggle-${graded.seq}`}
        aria-expanded={open}
        onPress={onToggle}
        className="flex h-auto items-center gap-1.5 bg-transparent px-0 py-1 text-xs font-medium text-success hover:underline"
      >
        <span aria-hidden="true">{open ? "▾" : "▸"}</span>
        {verdicts.length} evaluation{verdicts.length > 1 ? "s" : ""}
      </Button>

      {open && (
        <ul
          className="flex flex-col gap-1 pb-1"
          data-testid={`history-evals-${graded.seq}`}
        >
          {orderedVerdicts.map((verdict) => {
            const score = formatScore(verdict.payload.overall_score);
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
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  data-testid={`history-eval-${verdict.seq}`}
                  aria-current={
                    selectedSeq === verdict.seq ? "true" : undefined
                  }
                  aria-expanded={vOpen}
                  onPress={() => {
                    onSelect(verdict.seq);
                    toggleVerdict(verdict.seq);
                  }}
                  data-level={level}
                  className={[
                    "flex h-auto w-full flex-col items-stretch gap-0.5 rounded-md border px-2 py-1.5 text-left transition-colors",
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
                    {score && (
                      <Chip
                        size="sm"
                        variant="primary"
                        color="success"
                        data-testid={`history-eval-score-${verdict.seq}`}
                      >
                        {score}
                      </Chip>
                    )}
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
                </Button>
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
  verdicts: HistoryEvent[];
  selected: boolean;
  selectedSeq: number | null;
  onSelect: (seq: number) => void;
  // Inline per-event actions, only rendered on the focused event.
  onRestore: (targetSeq: number, mode: RestoreMode) => Promise<RestoreOutcome>;
  board: BoardActions;
  // Global expand/collapse pulse — each event syncs its body to this on change.
  expandSignal: ExpandSignal;
  // Reveal pulse — open this event's body or evals when it is the target.
  reveal: RevealSignal;
}

function TranscriptEvent({
  event,
  step,
  verdicts,
  selected,
  selectedSeq,
  onSelect,
  onRestore,
  board,
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

  const latestScore =
    verdicts.length > 0
      ? formatScore(verdicts[verdicts.length - 1].payload.overall_score)
      : null;

  return (
    <div className="flex flex-col">
      <Card
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
              {phaseName(step)} {step}
            </Chip>
          )}
          {latestScore && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              data-testid={`history-event-eval-indicator-${event.seq}`}
              onPress={() => {
                onSelect(event.seq);
                revealEvals();
              }}
              onClick={(e) => e.stopPropagation()}
              className="h-auto rounded-full bg-transparent p-0"
            >
              {/* Hero UI's Button props do not accept `title`; the tooltip
                  lives on the score chip it wraps. */}
              <Chip
                size="sm"
                variant="primary"
                color="success"
                title="View evaluation"
              >
                {latestScore}
              </Chip>
            </Button>
          )}
          <span className="ml-auto text-xs text-default-400">
            {hhmmss(event.occurred_at)}
          </span>
          <div className="relative" ref={actionsRef}>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              data-testid={`history-event-actions-toggle-${event.seq}`}
              aria-expanded={showActions}
              aria-haspopup="menu"
              onPress={() => {
                onSelect(event.seq);
                setShowActions((p) => !p);
              }}
              onClick={(e) => e.stopPropagation()}
              className="h-auto rounded-md border border-default-200/60 bg-transparent px-2 py-0.5 text-xs text-default-500 transition-colors hover:bg-default-100 hover:text-foreground"
            >
              Actions {showActions ? "▾" : "▸"}
            </Button>
            {showActions && (
              <Card
                role="menu"
                data-testid={`history-event-actions-${event.seq}`}
                onClick={(e) => e.stopPropagation()}
                className="absolute right-0 top-full z-30 mt-1 flex w-72 flex-col gap-2 rounded-xl border border-default-200/60 bg-background p-2 shadow-xl"
              >
                <RestoreControl targetSeq={event.seq} onRestore={onRestore} />
                <BoardOpenControl
                  gameId={board.gameId}
                  selectedSeq={event.seq}
                  isOpening={board.isOpening}
                  error={board.error}
                  isOpen={board.isOpen}
                  onOpen={board.onOpen}
                />
              </Card>
            )}
          </div>
        </div>

        {isUser ? (
          <span className="text-sm font-medium text-foreground">
            {actionLabel(event)}
          </span>
        ) : (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            data-testid={`history-event-body-toggle-${event.seq}`}
            aria-expanded={bodyOpen}
            onPress={() => {
              onSelect(event.seq);
              setBodyOpen((p) => !p);
            }}
            onClick={(e) => e.stopPropagation()}
            className="flex h-auto items-center gap-1.5 self-start bg-transparent px-0 text-left text-sm font-medium text-foreground transition-colors hover:text-primary hover:underline"
          >
            <span aria-hidden="true" className="text-xs text-default-400">
              {bodyOpen ? "▾" : "▸"}
            </span>
            {actionLabel(event)}
          </Button>
        )}

        {isUser ? (
          <UserBody event={event} />
        ) : bodyOpen && isAgent ? (
          <AgentBody event={event} />
        ) : bodyOpen ? (
          <GameBody event={event} />
        ) : null}
      </Card>

      {verdicts.length > 0 && (
        <div ref={evalsRef}>
          <VerdictSubtree
            graded={event}
            verdicts={verdicts}
            selectedSeq={selectedSeq}
            onSelect={onSelect}
            open={evalsOpen}
            onToggle={() => setEvalsOpen((p) => !p)}
          />
        </div>
      )}
    </div>
  );
}

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
  expandSignal = { generation: 0, expanded: false },
  searchQuery = "",
  reveal = { seq: null, mode: "body", nonce: 0 },
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
    scrollToBottom();
  }, [scrollToBottom]);

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
  // changes, never re-running on re-render or fighting the auto-follow lock.
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
  }, [selectedSeq]);

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
          {primary.map((event) => {
            const meta = metaBySeq.get(event.seq) ?? {
              round: null,
              step: null,
            };
            const heading = headingBySeq.get(event.seq) ?? null;
            const roundEnd = roundEndBySeq.get(event.seq) ?? null;
            const verdicts = evalsByTarget.get(event.seq) ?? [];
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
                    verdicts={verdicts}
                    selected={selectedSeq === event.seq}
                    selectedSeq={selectedSeq}
                    onSelect={onSelect}
                    onRestore={onRestore}
                    board={board}
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
          <div ref={bottomRef} />
        </div>
      </div>

      {!isLocked && (
        <Button
          data-testid="history-jump-to-latest"
          type="button"
          variant="ghost"
          size="sm"
          aria-label="Jump to latest"
          className="absolute bottom-4 right-4 z-10 flex h-auto items-center gap-1.5 rounded-full border border-default-200/60 bg-background/90 px-3 py-1.5 text-xs font-medium text-default-600 shadow-lg backdrop-blur-sm transition-colors hover:bg-default-100 hover:text-foreground"
          onPress={jumpToLatest}
        >
          <span aria-hidden="true">↓</span>
          Jump to latest
        </Button>
      )}
    </div>
  );
}
