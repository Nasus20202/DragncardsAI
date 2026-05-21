import {
  JobDetail,
  JobEventResponse,
  JobSummary,
  JsonValue,
} from "@/features/shared/lib/types";

export type AggEvent =
  | { kind: "reasoning"; text: string }
  | { kind: "model_output"; text: string }
  | { kind: "compaction"; text: string }
  | { kind: "tool_call"; event: JobEventResponse }
  | { kind: "tool_result"; event: JobEventResponse }
  | { kind: "skill_loaded"; event: JobEventResponse }
  | { kind: "subagent_started"; event: JobEventResponse }
  | { kind: "subagent_completed"; event: JobEventResponse }
  | { kind: "subagent_failed"; event: JobEventResponse }
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
export const STREAM_EVENT_TYPES = [
  "progress",
  "reasoning",
  "model_output",
  "compaction",
  "tool_call",
  "tool_result",
  "completion",
  "failure",
  "cancellation",
  "skill_loaded",
  "subagent_started",
  "subagent_completed",
  "subagent_failed",
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

      case "tool_call":
      case "tool_result":
      case "skill_loaded":
      case "subagent_started":
      case "subagent_completed":
      case "subagent_failed":
      case "failure":
      case "cancellation":
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
        result.push({ kind: "tool_call", event });
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
