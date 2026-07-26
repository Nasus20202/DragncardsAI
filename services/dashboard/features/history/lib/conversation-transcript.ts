import { JsonValue } from "@/features/shared/lib/types";

/**
 * Maps an agent move's captured `conversation_context` (an OpenAI-format
 * message array) into renderable transcript items, mirroring the Play tab's
 * presentation (message bubbles, collapsible reasoning, tool-call/result
 * cards). This is the history counterpart to Play's job-event aggregation:
 * Play consumes orchestrator job events, history consumes OpenAI messages, so
 * the two share the presentational pieces but not the source format.
 */

/** A tool call requested by an assistant message. */
export interface TranscriptToolCall {
  id: string;
  name: string;
  /** Pretty-printed JSON (or the raw string) of the call arguments. */
  arguments: string;
}

export type TranscriptItem =
  | { kind: "system"; text: string }
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string }
  | { kind: "tool_call"; call: TranscriptToolCall }
  | {
      kind: "tool_result";
      /** The tool_call_id this result answers, if known. */
      toolCallId: string | null;
      /** Resolved tool name, paired from the originating tool_call. */
      name: string | null;
      text: string;
    };

interface RawToolCall {
  id?: unknown;
  function?: { name?: unknown; arguments?: unknown };
}

interface RawMessage {
  role?: unknown;
  content?: unknown;
  tool_calls?: unknown;
  tool_call_id?: unknown;
  name?: unknown;
}

function asString(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

/**
 * OpenAI message `content` can be a string or an array of content parts
 * (e.g. `{type:"text", text}`); flatten either into a single readable string.
 */
function contentToText(content: unknown): string {
  if (content === null || content === undefined) return "";
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === "string") return part;
        if (part && typeof part === "object") {
          const text = (part as Record<string, unknown>).text;
          if (typeof text === "string") return text;
        }
        return asString(part);
      })
      .filter(Boolean)
      .join("\n");
  }
  return asString(content);
}

function prettyArguments(value: unknown): string {
  if (typeof value === "string") {
    // tool_call arguments are commonly a JSON-encoded string; pretty-print it
    // when it parses, otherwise fall back to the raw string.
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  }
  return asString(value);
}

function parseToolCalls(raw: unknown): TranscriptToolCall[] {
  if (!Array.isArray(raw)) return [];
  const calls: TranscriptToolCall[] = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== "object") continue;
    const call = entry as RawToolCall;
    const id = typeof call.id === "string" ? call.id : "";
    const name =
      call.function && typeof call.function.name === "string"
        ? call.function.name
        : "tool";
    const args = call.function ? call.function.arguments : undefined;
    calls.push({ id, name, arguments: prettyArguments(args) });
  }
  return calls;
}

/**
 * Convert an OpenAI-format message array into ordered transcript items. Tool
 * results are paired back to their originating tool call (by `tool_call_id`)
 * so the rendered result card can show the tool name.
 */
export function mapConversationToTranscript(
  context: JsonValue | undefined | null
): TranscriptItem[] {
  if (!Array.isArray(context)) return [];

  // First pass: index tool-call names by id so results can resolve a name.
  const toolNameById = new Map<string, string>();
  for (const entry of context) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
    const message = entry as RawMessage;
    if (message.role === "assistant") {
      for (const call of parseToolCalls(message.tool_calls)) {
        if (call.id) toolNameById.set(call.id, call.name);
      }
    }
  }

  const items: TranscriptItem[] = [];
  for (const entry of context) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
    const message = entry as RawMessage;
    const role = typeof message.role === "string" ? message.role : "";
    const text = contentToText(message.content);

    switch (role) {
      case "system":
        if (text) items.push({ kind: "system", text });
        break;
      case "user":
        if (text) items.push({ kind: "user", text });
        break;
      case "assistant": {
        if (text) items.push({ kind: "assistant", text });
        for (const call of parseToolCalls(message.tool_calls)) {
          items.push({ kind: "tool_call", call });
        }
        break;
      }
      case "tool": {
        const toolCallId =
          typeof message.tool_call_id === "string"
            ? message.tool_call_id
            : null;
        const name =
          (toolCallId && toolNameById.get(toolCallId)) ||
          (typeof message.name === "string" ? message.name : null);
        items.push({
          kind: "tool_result",
          toolCallId,
          name,
          text,
        });
        break;
      }
      default:
        // Unknown role — surface its content so nothing is silently dropped.
        if (text) items.push({ kind: "assistant", text });
        break;
    }
  }

  return items;
}
