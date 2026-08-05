import {
  JobDetail,
  JobEventResponse,
  JobSummary,
  JsonValue,
  UserQuestionClosedReason,
} from "@/features/shared/lib/types";

export type AggEvent =
  | { kind: "reasoning"; text: string }
  | { kind: "model_output"; text: string }
  | { kind: "compaction"; text: string }
  /**
   * Compaction was attempted and could not complete. The turn it was protecting
   * still ran, on the history it already had — this row exists so that
   * degradation is visible instead of silent.
   */
  | { kind: "compaction_failed"; event: JobEventResponse }
  /**
   * The provider cut the model off at its output token limit and the service
   * resumed the turn by itself. Its own row because the alternative — two
   * output blocks with nothing between them — reads as one answer the model
   * chose to write in two parts, which is not what happened.
   */
  | { kind: "turn_continued"; event: JobEventResponse }
  /**
   * One tool invocation: the call, and its result once it has arrived. The two
   * events are paired by `tool_call_id` rather than shown as two separate cards,
   * because a tool's name, its arguments and its answer are one thing to read —
   * and because a call with no result yet is exactly what "still running" means.
   */
  | {
      kind: "tool_exchange";
      call: JobEventResponse | null;
      result: JobEventResponse | null;
    }
  | { kind: "skill_loaded"; event: JobEventResponse }
  | { kind: "subagent_started"; event: JobEventResponse }
  | { kind: "subagent_completed"; event: JobEventResponse }
  | { kind: "subagent_failed"; event: JobEventResponse }
  | { kind: "user_question"; event: JobEventResponse }
  /**
   * A tool call a player seat made was refused before it reached the tool,
   * because one of its arguments named another seat's cards. Its own row rather
   * than a tool exchange: no tool ran, so there is no call/result pair to show,
   * and the point of the row is that the boundary held.
   */
  | { kind: "seat_scope_violation"; event: JobEventResponse }
  /**
   * The orchestrator recorded (or resolved) a finding that a seat's action broke
   * the rules. Opening and resolving are the same event type carrying different
   * `status` values, so the transcript shows both halves of one finding's life.
   */
  | { kind: "illegal_action_finding"; event: JobEventResponse }
  | { kind: "failure"; event: JobEventResponse }
  | { kind: "cancellation"; event: JobEventResponse };

export interface SubagentEntry {
  childJobId: string;
  childSessionId: string;
  status: "running" | "completed" | "failed";
  name?: string;
  reason?: string;
}

export const TERMINAL_EVENT_TYPES = new Set([
  "completion",
  "failure",
  "cancellation",
]);
export const SUBAGENT_TERMINAL_EVENT_TYPES = new Set([
  "subagent_completed",
  "subagent_failed",
]);
/**
 * Job statuses that mean the job will never run again, so a question it left
 * pending can no longer be answered.
 */
export const TERMINAL_JOB_STATUSES = new Set([
  "completed",
  "failed",
  "cancelled",
  "interrupted",
]);
/**
 * Every SSE event name the job stream listens for. `use-job-streaming`
 * registers one named listener per entry — there is deliberately no
 * `onmessage` fallback — so an event type missing here is silently dropped.
 */
export const STREAM_EVENT_TYPES = [
  "progress",
  "reasoning",
  "model_output",
  "compaction",
  "compaction_failed",
  "tool_call",
  "tool_result",
  "completion",
  "failure",
  "cancellation",
  "skill_loaded",
  "subagent_started",
  "subagent_completed",
  "subagent_failed",
  "user_question",
  "user_question_answered",
  "user_question_closed",
  "seat_scope_violation",
  "illegal_action_finding",
  // Deliberately not in TERMINAL_EVENT_TYPES: a continued turn is still running.
  "turn_continued",
] as const;

function sameEventPayload(
  left: JobEventResponse,
  right: JobEventResponse
): boolean {
  return (
    left.event_type === right.event_type &&
    JSON.stringify(left.payload) === JSON.stringify(right.payload)
  );
}

function sortEventsOldestFirst(
  left: JobEventResponse,
  right: JobEventResponse
) {
  return (
    new Date(left.created_at).getTime() - new Date(right.created_at).getTime()
  );
}

function eventHasCompactionPayload(event: JobEventResponse): boolean {
  return event.payload.compaction === true;
}

export function compareJobsOldestFirst(left: JobSummary, right: JobSummary) {
  return (
    new Date(left.created_at).getTime() - new Date(right.created_at).getTime()
  );
}

export function mergeJob(jobs: JobDetail[], updated: JobDetail): JobDetail[] {
  const existing = jobs.findIndex((job) => job.id === updated.id);
  if (existing >= 0) {
    const next = [...jobs];
    next[existing] = updated;
    return next;
  }
  return [...jobs, updated].sort(compareJobsOldestFirst);
}

export function upsertStreamEvent(
  events: JobEventResponse[],
  incoming: JobEventResponse
): JobEventResponse[] {
  const isStreamChunk =
    (incoming.event_type === "model_output" ||
      incoming.event_type === "reasoning") &&
    incoming.payload.stream === true;
  const snapshotEventId =
    typeof incoming.payload.snapshot_event_id === "string"
      ? incoming.payload.snapshot_event_id
      : null;

  if (isStreamChunk && snapshotEventId) {
    const normalizedPayload: Record<string, JsonValue> = {
      ...incoming.payload,
    };
    delete normalizedPayload.stream;
    delete normalizedPayload.snapshot_event_id;
    const normalizedEvent: JobEventResponse = {
      ...incoming,
      id: snapshotEventId,
      payload: normalizedPayload,
    };
    const existingIndex = events.findIndex(
      (event) => event.id === snapshotEventId
    );
    if (existingIndex >= 0) {
      const existing = events[existingIndex];
      const updated = {
        ...normalizedEvent,
        created_at: existing.created_at,
      };
      if (sameEventPayload(existing, updated)) {
        return events;
      }
      const next = [...events];
      next[existingIndex] = updated;
      return next;
    }
    return [...events, normalizedEvent].sort(sortEventsOldestFirst);
  }

  const existingIndex = events.findIndex((event) => event.id === incoming.id);
  if (existingIndex >= 0) {
    const existing = events[existingIndex];
    if (sameEventPayload(existing, incoming)) {
      return events;
    }
    const next = [...events];
    next[existingIndex] = incoming;
    return next;
  }

  return [...events, incoming].sort(sortEventsOldestFirst);
}

export function applyStreamEventToJob(
  job: JobDetail,
  payload: JobEventResponse
): JobDetail | null {
  const nextEvents = upsertStreamEvent(job.events, payload);
  if (nextEvents === job.events) {
    return null;
  }

  const isTerminal = TERMINAL_EVENT_TYPES.has(payload.event_type);
  return {
    ...job,
    events: nextEvents,
    latest_event_id: payload.id,
    latest_event_type: payload.event_type,
    status: isTerminal
      ? payload.event_type === "completion"
        ? "completed"
        : payload.event_type === "cancellation"
          ? "cancelled"
          : "failed"
      : job.status,
    outputs:
      payload.event_type === "completion" &&
      typeof payload.payload.text === "string"
        ? [payload.payload.text, ...job.outputs].filter(Boolean)
        : job.outputs,
  };
}

/* ── Model-initiated questions (`ask_user`) ──────────────────────── */

/**
 * One offered answer, as the transcript consumes it.
 *
 * SECURITY: every field here is model-authored. Render as plain text children
 * only — never through markdown, `dangerouslySetInnerHTML`, or a resolved
 * attribute — and never use `value` as a React key (choices may repeat one).
 */
export interface UserQuestionChoice {
  label: string;
  value: string;
  description?: string;
}

/** A `user_question` event, validated into the shape the card renders. */
export interface UserQuestionPrompt {
  questionId: string;
  /** Model-authored; see the security note on `UserQuestionChoice`. */
  question: string;
  choices: UserQuestionChoice[];
  allowFreeText: boolean;
}

/**
 * Whether a question is still awaiting an answer, and what settled it.
 *
 * Always derived from the job's durable event list rather than held as its own
 * state: the orchestrator persists all three question event types in
 * `job_events` and the dashboard replays from `after=0` on reconnect, so a page
 * reload restores the resolved state with no extra fetch.
 */
export type UserQuestionResolution =
  | { status: "pending" }
  | {
      status: "answered";
      source: "choice" | "free_text";
      value: string | null;
      label: string | null;
      text: string | null;
    }
  | {
      status: "closed";
      reason: UserQuestionClosedReason;
      waitedSeconds: number | null;
    };

function payloadString(value: JsonValue | undefined): string | null {
  return typeof value === "string" ? value : null;
}

/**
 * Read a `user_question` event, or null when the payload does not carry a
 * usable question. Choices that are not `{label, value}` string pairs are
 * dropped rather than rendered half-formed.
 */
export function parseUserQuestionEvent(
  event: JobEventResponse
): UserQuestionPrompt | null {
  const questionId = payloadString(event.payload.question_id);
  const question = payloadString(event.payload.question);
  if (!questionId || question === null) {
    return null;
  }

  const rawChoices = Array.isArray(event.payload.choices)
    ? event.payload.choices
    : [];
  const choices: UserQuestionChoice[] = [];
  for (const raw of rawChoices) {
    if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
      continue;
    }
    const label = payloadString(raw.label);
    const value = payloadString(raw.value);
    if (label === null || value === null) {
      continue;
    }
    const description = payloadString(raw.description);
    choices.push(
      description === null ? { label, value } : { label, value, description }
    );
  }

  return {
    questionId,
    question,
    choices,
    allowFreeText: event.payload.allow_free_text === true,
  };
}

/**
 * Fold the question events of one job into a per-question resolution. The
 * answered/closed events render no transcript row of their own; they resolve
 * the question row that the `user_question` event produced.
 */
export function deriveUserQuestionResolutions(
  events: JobEventResponse[]
): Map<string, UserQuestionResolution> {
  const resolutions = new Map<string, UserQuestionResolution>();
  for (const event of events) {
    const questionId = payloadString(event.payload.question_id);
    if (!questionId) {
      continue;
    }
    switch (event.event_type) {
      case "user_question":
        // Never downgrade an already-settled question: a replay could hand the
        // question back after its resolution.
        if (!resolutions.has(questionId)) {
          resolutions.set(questionId, { status: "pending" });
        }
        break;
      case "user_question_answered":
        resolutions.set(questionId, {
          status: "answered",
          source: event.payload.source === "free_text" ? "free_text" : "choice",
          value: payloadString(event.payload.value),
          label: payloadString(event.payload.label),
          text: payloadString(event.payload.text),
        });
        break;
      case "user_question_closed":
        resolutions.set(questionId, {
          status: "closed",
          reason:
            event.payload.reason === "cancelled" ? "cancelled" : "timeout",
          waitedSeconds:
            typeof event.payload.waited_seconds === "number"
              ? event.payload.waited_seconds
              : null,
        });
        break;
    }
  }
  return resolutions;
}

/* ── Orchestrated-mode boundary events ───────────────────────────── */

/**
 * A refused seat-scoped tool call, as the transcript consumes it.
 *
 * `argument`/`value` are model-authored (they came out of the tool call the seat
 * attempted); the seat ids and the message are server-authored. Everything here
 * is rendered as plain text children only.
 */
export interface SeatScopeViolation {
  playerId: string;
  foreignPlayerId: string;
  toolName: string;
  argument: string;
  value: string;
  message: string;
}

/** An illegal-action finding the orchestrator opened or resolved. */
export interface IllegalActionFinding {
  findingId: string;
  playerId: string;
  violation: string;
  requiredUndo: string;
  status: "open" | "resolved";
  roundNumber: number | null;
  resolutionNote: string | null;
}

/**
 * Read a `seat_scope_violation` event, or null when the payload does not name
 * both the caller's seat and the foreign seat — without those two the row would
 * not say what it exists to say, so the generic block is a better fallback.
 */
export function parseSeatScopeViolationEvent(
  event: JobEventResponse
): SeatScopeViolation | null {
  const playerId = payloadString(event.payload.player_id);
  const foreignPlayerId = payloadString(event.payload.foreign_player_id);
  if (!playerId || !foreignPlayerId) {
    return null;
  }
  return {
    playerId,
    foreignPlayerId,
    toolName: payloadString(event.payload.tool_name) ?? "",
    argument: payloadString(event.payload.argument) ?? "",
    value: payloadString(event.payload.value) ?? "",
    message: payloadString(event.payload.message) ?? "",
  };
}

/**
 * Read an `illegal_action_finding` event, or null when the payload does not name
 * the seat the finding concerns. `status` is narrowed here rather than at the
 * call site so an unrecognised value reads as `open` — an unresolved finding is
 * the safe way to be wrong about one.
 */
export function parseIllegalActionFindingEvent(
  event: JobEventResponse
): IllegalActionFinding | null {
  const playerId = payloadString(event.payload.player_id);
  if (!playerId) {
    return null;
  }
  return {
    findingId: payloadString(event.payload.finding_id) ?? "",
    playerId,
    violation: payloadString(event.payload.violation) ?? "",
    requiredUndo: payloadString(event.payload.required_undo) ?? "",
    status: event.payload.status === "resolved" ? "resolved" : "open",
    roundNumber:
      typeof event.payload.round_number === "number"
        ? event.payload.round_number
        : null,
    resolutionNote: payloadString(event.payload.resolution_note),
  };
}

export function compactionText(event: JobEventResponse): string {
  if (typeof event.payload.summary_text === "string") {
    return event.payload.summary_text;
  }
  if (typeof event.payload.text === "string") {
    return event.payload.text;
  }
  return JSON.stringify(event.payload, null, 2);
}

export function eventBodyText(event: JobEventResponse): string {
  const payload = event.payload;
  if (typeof payload.text === "string") return payload.text;
  if (typeof payload.summary_text === "string") return payload.summary_text;
  if (typeof payload.message === "string") return payload.message;
  return JSON.stringify(payload, null, 2);
}

export function aggregateEvents(
  events: JobEventResponse[],
  isCompactionJob: boolean
): AggEvent[] {
  // When a job has multiple attempts (retry), intermediate failure events are
  // followed by another progress event. Keep only the last failure per job so
  // the UI doesn't show duplicate error cards.
  const lastFailureIndex = events.reduce<number>(
    (acc, event, i) => (event.event_type === "failure" ? i : acc),
    -1
  );
  const filteredEvents = events.filter(
    (event, i) => event.event_type !== "failure" || i === lastFailureIndex
  );

  // Index the results by the call they answer so a call can be rendered with
  // its result even when other events, or other parallel tool calls, sit
  // between the two. Building the index costs one pass over the same list the
  // aggregation already walks; it does not read into any payload.
  const resultsByCallId = new Map<string, JobEventResponse>();
  for (const event of filteredEvents) {
    if (event.event_type !== "tool_result") {
      continue;
    }
    const callId = event.payload.tool_call_id;
    if (typeof callId === "string" && callId && !resultsByCallId.has(callId)) {
      resultsByCallId.set(callId, event);
    }
  }
  const pairedResults = new Set<JobEventResponse>();

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

  for (const event of filteredEvents) {
    switch (event.event_type) {
      case "progress":
        break;

      case "completion": {
        flushReasoning();
        const completionText =
          typeof event.payload.text === "string" ? event.payload.text : "";
        if (completionText) {
          modelText = completionText;
        }
        break;
      }

      case "reasoning":
        reasoningText +=
          typeof event.payload.text === "string" ? event.payload.text : "";
        break;

      case "model_output":
        if (isCompactionJob || eventHasCompactionPayload(event)) {
          flushReasoning();
          flushModel();
          result.push({ kind: "compaction", text: compactionText(event) });
          break;
        }
        flushReasoning();
        modelText +=
          typeof event.payload.text === "string" ? event.payload.text : "";
        break;

      // A question is its own transcript row, not a collapsible tool block.
      // Its answered/closed siblings deliberately produce no row: they resolve
      // the row this one created (see `deriveUserQuestionResolutions`).
      case "user_question_answered":
      case "user_question_closed":
        break;

      case "tool_call": {
        flushReasoning();
        flushModel();
        const callId = event.payload.tool_call_id;
        const paired =
          typeof callId === "string" && callId
            ? (resultsByCallId.get(callId) ?? null)
            : null;
        if (paired) {
          pairedResults.add(paired);
        }
        result.push({ kind: "tool_exchange", call: event, result: paired });
        break;
      }

      case "tool_result":
        flushReasoning();
        flushModel();
        // A result already shown next to its call is not repeated. One that has
        // no call to attach to — a truncated event window, or a payload with no
        // `tool_call_id` — is still shown, so nothing is silently dropped.
        if (!pairedResults.has(event)) {
          result.push({ kind: "tool_exchange", call: null, result: event });
        }
        break;

      case "skill_loaded":
      case "subagent_started":
      case "subagent_completed":
      case "subagent_failed":
      case "user_question":
      case "seat_scope_violation":
      case "illegal_action_finding":
      case "failure":
      case "cancellation":
      case "compaction_failed":
      case "turn_continued":
      case "compaction":
        flushReasoning();
        flushModel();
        if (event.event_type === "compaction") {
          result.push({ kind: "compaction", text: compactionText(event) });
        } else {
          result.push({ kind: event.event_type, event });
        }
        break;

      default:
        flushReasoning();
        flushModel();
        result.push({ kind: "tool_exchange", call: event, result: null });
        break;
    }
  }

  flushReasoning();
  flushModel();
  return result;
}

export function deriveSubagentEntries(
  jobs: JobDetail[],
  childJobStatuses?: Map<string, string>
): SubagentEntry[] {
  const byId = new Map<string, SubagentEntry>();
  for (const job of jobs) {
    for (const event of job.events) {
      const payload = event.payload as Record<string, unknown>;
      const childJobId =
        typeof payload.child_job_id === "string" ? payload.child_job_id : null;
      if (!childJobId) {
        continue;
      }

      const childSessionId =
        typeof payload.child_session_id === "string"
          ? payload.child_session_id
          : "";
      const name = typeof payload.name === "string" ? payload.name : undefined;
      if (event.event_type === "subagent_started") {
        if (!byId.has(childJobId)) {
          byId.set(childJobId, {
            childJobId,
            childSessionId,
            status: "running",
            name,
          });
        }
        continue;
      }

      const existing = byId.get(childJobId);
      if (!existing) {
        continue;
      }

      if (event.event_type === "subagent_completed") {
        byId.set(childJobId, { ...existing, status: "completed" });
      }

      if (event.event_type === "subagent_failed") {
        byId.set(childJobId, {
          ...existing,
          status: "failed",
          reason:
            typeof payload.reason === "string"
              ? payload.reason
              : existing.reason,
        });
      }
    }
  }

  if (childJobStatuses) {
    for (const [childJobId, entry] of byId) {
      if (entry.status !== "running") continue;
      const dbStatus = childJobStatuses.get(childJobId);
      if (!dbStatus || dbStatus === "queued" || dbStatus === "running") {
        continue;
      }
      byId.set(childJobId, {
        ...entry,
        status: dbStatus === "completed" ? "completed" : "failed",
      });
    }
  }

  return Array.from(byId.values());
}

export function listUnresolvedSubagentJobIds(jobs: JobDetail[]): string[] {
  const started = new Set<string>();
  const resolved = new Set<string>();
  for (const job of jobs) {
    for (const event of job.events) {
      const payload = event.payload as Record<string, unknown>;
      const childJobId =
        typeof payload.child_job_id === "string" ? payload.child_job_id : null;
      if (!childJobId) {
        continue;
      }
      if (event.event_type === "subagent_started") {
        started.add(childJobId);
      }
      if (SUBAGENT_TERMINAL_EVENT_TYPES.has(event.event_type)) {
        resolved.add(childJobId);
      }
    }
  }
  return [...started].filter((childJobId) => !resolved.has(childJobId));
}
