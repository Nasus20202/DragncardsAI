"use client";

import { Chip, Spinner } from "@heroui/react";
import { createContext, memo, useContext, useMemo, useState } from "react";
import { JobEventResponse, JsonValue } from "@/features/shared/lib/types";
import {
  BODY_VALUE_CHARS,
  RESULT_PREVIEW_CHARS,
  ToolExchangeView,
  argumentText,
  boundedArgumentText,
  boundedResultText,
  boundedValueText,
  buildToolExchangeView,
  presentationForTool,
  redactSecrets,
  shortId,
  subagentReference,
  toolResultText,
} from "@/features/play/lib/tool-call-presentation";

/**
 * Readable presentation of one tool invocation in the Play transcript.
 *
 * Before this existed the transcript showed two cards per call, each opening on
 * `JSON.stringify(payload, null, 2)` — the tool's name buried in a label and its
 * arguments and answer as a JSON blob. Here a call is one card: the tool's name,
 * a one-line summary of its arguments, and its state (running / done / failed),
 * with the named arguments and the result body behind the same collapse the rest
 * of the transcript uses.
 *
 * Two rules the renderers below all follow:
 *
 * - **Nothing large is read while collapsed.** Every value in a closed card
 *   comes from the bounded helpers in `tool-call-presentation`. The full text of
 *   an argument or a result is produced only inside an open body, and only when
 *   the reader asks for the whole of it. This is what keeps DRA-8's guarantee —
 *   per-update work bounded by what changed — true for a 400 kB board state.
 * - **Everything is text.** Arguments are model-supplied and results are
 *   server-supplied, so every string goes through the redaction in
 *   `tool-call-presentation` and is rendered as a text node. Nothing is
 *   interpolated as HTML.
 */

/* ── Opening the subagent an exchange refers to ──────────────────── */

interface ToolExchangeHandlers {
  /**
   * Open the existing subagent output view on a child job. Provided by the Play
   * workspace; absent inside that view itself, where the button would have
   * nothing to open.
   *
   * MUST be referentially stable across renders — the memoised cards below
   * consume it through this context, and an identity that changes every render
   * would re-render every tool card in the transcript.
   */
  onViewSubagent?: (childJobId: string, name: string) => void;
}

const ToolExchangeContext = createContext<ToolExchangeHandlers>({});

export function ToolExchangeProvider({
  onViewSubagent,
  children,
}: ToolExchangeHandlers & { children: React.ReactNode }) {
  const value = useMemo(() => ({ onViewSubagent }), [onViewSubagent]);
  return (
    <ToolExchangeContext.Provider value={value}>
      {children}
    </ToolExchangeContext.Provider>
  );
}

/* ── Shared card frame ───────────────────────────────────────────── */

/** Matches the transcript's other collapsible blocks exactly. */
const CARD_CLASS =
  "overflow-hidden rounded-lg border border-default-200/60 bg-default-50/40 dark:bg-white/3";
const BODY_CLASS = "border-t border-default-200/60 px-3 py-2.5";
const PRE_CLASS =
  "overflow-x-auto whitespace-pre-wrap break-words text-xs leading-relaxed text-default-600 dark:text-default-300";

function StatusDot({ status }: { status: ToolExchangeView["status"] }) {
  if (status === "pending") {
    return (
      <span
        aria-hidden="true"
        className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-default-400"
      />
    );
  }
  return (
    <span
      aria-hidden="true"
      className={`h-1.5 w-1.5 shrink-0 rounded-full ${
        status === "error" ? "bg-danger" : "bg-default-400"
      }`}
    />
  );
}

/**
 * The collapsible frame every tool card shares: a header that names the tool and
 * carries an optional accessory, and a body rendered only while open.
 */
function ToolCard({
  view,
  accessory,
  headline,
  children,
  testId,
}: {
  view: ToolExchangeView;
  /** Rendered to the right of the header, outside the toggle button. */
  accessory?: React.ReactNode;
  /** Replaces the argument summary on the header line. */
  headline?: React.ReactNode;
  children: React.ReactNode;
  testId?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className={CARD_CLASS} data-testid={testId ?? "tool-exchange"}>
      <div className="flex items-center gap-2 pr-2 transition-colors hover:bg-default-100/60">
        <button
          type="button"
          aria-expanded={open}
          aria-label={`${open ? "Collapse" : "Expand"} tool call: ${view.toolName}`}
          className="flex min-w-0 flex-1 items-center gap-2 px-3 py-2 text-left"
          onClick={() => setOpen((previous) => !previous)}
        >
          <StatusDot status={view.status} />
          <span className="shrink-0 font-mono text-xs font-medium text-default-600 dark:text-default-300">
            {view.toolName}
          </span>
          <span className="min-w-0 flex-1 truncate text-xs text-default-400">
            {headline ?? view.summary}
          </span>
          <span
            aria-hidden="true"
            className="shrink-0 text-xs text-default-400"
          >
            {open ? "▴" : "▾"}
          </span>
        </button>
        {accessory}
      </div>
      {open && <div className={BODY_CLASS}>{children}</div>}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-default-400">
      {children}
    </p>
  );
}

/**
 * One long value, shown up to a cap with the rest one click away. Keeping the
 * cap means a card cannot stretch the transcript to the height of a card list
 * just because it was opened.
 */
function ExpandableText({
  preview,
  truncated,
  full,
  label,
}: {
  preview: string;
  truncated: boolean;
  /** Produces the whole text; called only when the reader asks for it. */
  full: () => string;
  label: string;
}) {
  const [showAll, setShowAll] = useState(false);
  const text = showAll ? full() : preview;

  return (
    <>
      <pre className={PRE_CLASS}>{text}</pre>
      {truncated && !showAll && (
        <button
          type="button"
          className="mt-1 rounded text-[11px] text-default-500 underline-offset-2 hover:text-foreground hover:underline"
          onClick={() => setShowAll(true)}
        >
          Show all of {label}
        </button>
      )}
    </>
  );
}

function ArgumentRow({ name, value }: { name: string; value: JsonValue }) {
  // Named, so an argument whose *name* says it holds a credential is redacted —
  // the value alone carries no field name for the pattern match to catch.
  const preview = boundedArgumentText(name, value, BODY_VALUE_CHARS);

  return (
    <div className="flex flex-col gap-0.5 py-1 sm:flex-row sm:gap-3">
      <span
        className="shrink-0 font-mono text-[11px] text-default-500 sm:w-36 sm:truncate"
        title={name}
      >
        {name}
      </span>
      <div className="min-w-0 flex-1">
        <ExpandableText
          preview={preview.text}
          truncated={preview.truncated}
          full={() => argumentText(name, value)}
          label={name}
        />
      </div>
    </div>
  );
}

function ArgumentsSection({ view }: { view: ToolExchangeView }) {
  if (view.args.length === 0) {
    return (
      <>
        <SectionLabel>Arguments</SectionLabel>
        <pre className={PRE_CLASS}>
          {view.callFallback
            ? boundedValueText(view.callFallback, BODY_VALUE_CHARS).text
            : "none"}
        </pre>
      </>
    );
  }
  return (
    <>
      <SectionLabel>Arguments</SectionLabel>
      <div className="divide-y divide-default-200/40">
        {view.args.map((arg) => (
          <ArgumentRow key={arg.name} name={arg.name} value={arg.value} />
        ))}
      </div>
    </>
  );
}

function ResultSection({
  result,
  isError,
  label = "Result",
}: {
  result: JobEventResponse | null;
  isError: boolean;
  label?: string;
}) {
  if (!result) {
    return (
      <>
        <SectionLabel>{label}</SectionLabel>
        <p className="text-xs text-default-400">Still running…</p>
      </>
    );
  }
  const preview = boundedResultText(result, RESULT_PREVIEW_CHARS);
  return (
    <>
      <SectionLabel>{isError ? `${label} (error)` : label}</SectionLabel>
      <div className={isError ? "text-danger" : undefined}>
        <ExpandableText
          preview={preview.text || "(empty)"}
          truncated={preview.truncated}
          full={() => toolResultText(result)}
          label="the result"
        />
      </div>
    </>
  );
}

/** Provenance line: which server answered, and which call this was. */
function MetaLine({ view }: { view: ToolExchangeView }) {
  const pieces = [
    view.server ? `via ${view.server}` : null,
    view.toolCallId ? `call ${shortId(view.toolCallId)}` : null,
  ].filter(Boolean);
  if (pieces.length === 0) {
    return null;
  }
  return (
    <p className="mt-2 text-[10px] text-default-400">{pieces.join(" · ")}</p>
  );
}

function ErrorChip() {
  return (
    <Chip size="sm" variant="soft" color="danger" data-testid="tool-error-chip">
      error
    </Chip>
  );
}

function ViewSubagentButton({
  childJobId,
  name,
}: {
  childJobId: string;
  name: string;
}) {
  const { onViewSubagent } = useContext(ToolExchangeContext);
  if (!onViewSubagent) {
    return null;
  }
  return (
    <button
      type="button"
      data-testid="tool-view-subagent"
      className="shrink-0 rounded-md border border-default-200 bg-content1/95 px-2 py-0.5 text-[11px] text-default-600 transition-colors hover:bg-default-100 hover:text-foreground"
      onClick={() => onViewSubagent(childJobId, name)}
    >
      View subagent
    </button>
  );
}

/* ── Generic renderer ────────────────────────────────────────────── */

function GenericExchange({
  view,
  result,
}: {
  view: ToolExchangeView;
  call: JobEventResponse | null;
  result: JobEventResponse | null;
}) {
  return (
    <ToolCard
      view={view}
      accessory={
        view.status === "error" ? (
          <ErrorChip />
        ) : view.status === "pending" ? (
          <Spinner size="sm" aria-label="Tool call running" />
        ) : undefined
      }
    >
      <ArgumentsSection view={view} />
      <div className="mt-3">
        <ResultSection result={result} isError={view.status === "error"} />
      </div>
      <MetaLine view={view} />
    </ToolCard>
  );
}

/* ── System tools ────────────────────────────────────────────────── */

/**
 * `spawn_subagent` and `prompt_player_agent`. Both return immediately with the
 * child they started, so the useful thing to show is *which* child — and a way
 * into it. The prompt handed to the child is the argument that matters, so it is
 * the summary line rather than one entry in a list.
 */
function SubagentLaunchExchange({
  view,
  call,
  result,
}: {
  view: ToolExchangeView;
  call: JobEventResponse | null;
  result: JobEventResponse | null;
}) {
  const reference = subagentReference(call, result);
  const seat = view.args.find((arg) => arg.name === "player_id");
  const label = reference?.name ?? reference?.childJobId ?? "";

  return (
    <ToolCard
      view={view}
      testId="tool-exchange-subagent-launch"
      headline={
        <>
          {seat && typeof seat.value === "string"
            ? `${redactSecrets(seat.value)} · `
            : ""}
          {view.status === "pending"
            ? "starting…"
            : reference
              ? `started ${label}`
              : view.summary}
        </>
      }
      accessory={
        view.status === "error" ? (
          <ErrorChip />
        ) : reference ? (
          <ViewSubagentButton
            childJobId={reference.childJobId}
            name={reference.name ?? shortId(reference.childJobId)}
          />
        ) : undefined
      }
    >
      <ArgumentsSection view={view} />
      {reference && (
        <p className="mt-2 font-mono text-[11px] text-default-500">
          child job {reference.childJobId}
        </p>
      )}
      {view.status === "error" && (
        <div className="mt-3">
          <ResultSection result={result} isError />
        </div>
      )}
      <MetaLine view={view} />
    </ToolCard>
  );
}

/**
 * `wait_for_subagent`. A pending wait is the one tool call whose *state* is the
 * information: the parent agent is blocked and there is nothing else to read, so
 * the header carries a live spinner and announces itself rather than looking
 * like a finished call nobody expanded.
 */
function SubagentWaitExchange({
  view,
  call,
  result,
}: {
  view: ToolExchangeView;
  call: JobEventResponse | null;
  result: JobEventResponse | null;
}) {
  const reference = subagentReference(call, result);
  const childLabel = reference ? shortId(reference.childJobId) : "subagent";
  const pending = view.status === "pending";

  return (
    <ToolCard
      view={view}
      testId="tool-exchange-subagent-wait"
      headline={
        pending ? (
          <span
            role="status"
            aria-live="polite"
            className="flex min-w-0 items-center gap-2"
            data-testid="tool-wait-spinner"
          >
            <Spinner size="sm" aria-label="Waiting for subagent" />
            <span className="truncate">waiting for {childLabel}…</span>
          </span>
        ) : (
          `${view.status === "error" ? "gave up on" : "collected"} ${childLabel}`
        )
      }
      accessory={
        <>
          {view.status === "error" && <ErrorChip />}
          {reference && (
            <ViewSubagentButton
              childJobId={reference.childJobId}
              name={reference.name ?? childLabel}
            />
          )}
        </>
      }
    >
      <ArgumentsSection view={view} />
      <div className="mt-3">
        <ResultSection
          result={result}
          isError={view.status === "error"}
          label="Subagent report"
        />
      </div>
      <MetaLine view={view} />
    </ToolCard>
  );
}

/**
 * `load_skill` and `load_skill_reference`. The arguments are one or two names
 * and the result is a whole markdown document, so the name belongs on the header
 * and the document belongs behind the collapse — which is what the generic
 * renderer would nearly do, except that it would put the names in a summary that
 * reads like a JSON fragment.
 */
function SkillLoadExchange({
  view,
  result,
}: {
  view: ToolExchangeView;
  call: JobEventResponse | null;
  result: JobEventResponse | null;
}) {
  const skill = view.args.find((arg) => arg.name === "skill_name");
  const reference = view.args.find((arg) => arg.name === "reference_name");
  const names = redactSecrets(
    [skill?.value, reference?.value]
      .filter(
        (value): value is string => typeof value === "string" && value !== ""
      )
      .join(" / ")
  );

  return (
    <ToolCard
      view={view}
      testId="tool-exchange-skill-load"
      headline={names || view.summary}
      accessory={
        view.status === "error" ? (
          <ErrorChip />
        ) : view.status === "pending" ? (
          <Spinner size="sm" aria-label="Loading skill" />
        ) : (
          <span className="shrink-0 text-[10px] text-default-400">
            {view.resultChars.toLocaleString()} chars
          </span>
        )
      }
    >
      <ArgumentsSection view={view} />
      <div className="mt-3">
        <ResultSection
          result={result}
          isError={view.status === "error"}
          label="Skill content"
        />
      </div>
      <MetaLine view={view} />
    </ToolCard>
  );
}

/* ── Registry ────────────────────────────────────────────────────── */

type ToolExchangeRenderer = (props: {
  view: ToolExchangeView;
  call: JobEventResponse | null;
  result: JobEventResponse | null;
}) => React.ReactElement;

/**
 * Presentation → renderer. To give a new system tool a bespoke card, add it to
 * `TOOL_PRESENTATIONS` in `tool-call-presentation.ts` and add the renderer here;
 * everything else keeps the generic card, which is why an unknown MCP tool still
 * reads well.
 */
const RENDERERS: Record<string, ToolExchangeRenderer> = {
  generic: GenericExchange,
  subagent_launch: SubagentLaunchExchange,
  subagent_wait: SubagentWaitExchange,
  skill_load: SkillLoadExchange,
};

/**
 * One tool invocation. Memoised on the two events it renders: their identities
 * are preserved by `upsertStreamEvent` unless their payloads actually changed,
 * so a streamed token elsewhere in the job leaves this card alone.
 */
export const ToolExchangeBlock = memo(function ToolExchangeBlock({
  call,
  result,
}: {
  call: JobEventResponse | null;
  result: JobEventResponse | null;
}) {
  const view = buildToolExchangeView(call, result);
  const Renderer =
    RENDERERS[presentationForTool(view.toolName)] ?? RENDERERS.generic;
  return <Renderer view={view} call={call} result={result} />;
});
