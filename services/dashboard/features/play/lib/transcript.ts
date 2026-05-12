import { JobEventResponse, JobSummary } from "@/features/shared/lib/types";

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

export function compareJobsOldestFirst(left: JobSummary, right: JobSummary) {
  return (
    new Date(left.created_at).getTime() - new Date(right.created_at).getTime()
  );
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

function eventHasCompactionPayload(event: JobEventResponse): boolean {
  return event.payload.compaction === true;
}

export function aggregateEvents(
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

  for (const event of events) {
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
