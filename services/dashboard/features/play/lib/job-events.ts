import {
  JobDetail,
  JobEventResponse,
  JsonValue,
} from "@/features/shared/lib/types";
import { compareJobsOldestFirst } from "@/features/play/lib/transcript";

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

  const isTerminal = ["completion", "failure", "cancellation"].includes(
    payload.event_type
  );
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
