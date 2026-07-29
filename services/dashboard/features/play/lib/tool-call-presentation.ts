import { JobEventResponse, JsonValue } from "@/features/shared/lib/types";

/**
 * Turns a `tool_call` / `tool_result` event pair into the values the transcript
 * needs to present it as a *readable* exchange rather than a JSON blob.
 *
 * Two properties matter as much as the readability:
 *
 * 1. **Cost is bounded by what is displayed, not by the payload.** A tool result
 *    can carry a whole board state or a card list, and DRA-8 established that
 *    per-update transcript work must not grow with the size of the history. So
 *    every value this module produces for a *collapsed* card is built through
 *    `boundedValueText`, which stops walking the payload once it has enough
 *    characters to fill the line. Nothing here serialises a whole payload; the
 *    full text is produced only by `toolResultText` / `toolValueText`, which the
 *    component calls from inside an already-expanded body.
 * 2. **Nothing rendered has been trusted.** Arguments come from the model and
 *    results come from MCP servers and provider gateways, so a result may carry
 *    an error body with a credential in it. Every string that leaves this module
 *    has passed through `redactSecrets`.
 */

/* ── Redaction ───────────────────────────────────────────────────── */

export const REDACTED = "[REDACTED]";

/*
 * Ported from `services/eval-service/src/eval_service/error_detail.py`, which
 * redacts the same shapes on the way into the evaluation store. The dashboard
 * needs its own copy because tool arguments and results never pass through the
 * eval service — they go straight from the orchestrator's job events to the
 * browser. Keep the two in step when either grows a pattern.
 */

// Credential-bearing field/header names followed by their value. A `:` or `=`
// separator is required so prose ("the secret is wrong") is not mangled, while
// header, JSON, env and query shapes are all covered. An optional `Bearer`
// prefix is consumed as part of the value so the token after it is replaced.
const SECRET_FIELD_RE =
  /\b(authorization|proxy-authorization|x-bf-api-key|x-api-key|x-goog-api-key|api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|id[_-]?token|auth[_-]?token|client[_-]?secret|secret|password|passwd)(["']?\s*[:=]\s*["']?)(?:bearer\s+)?[^\s"',;)}\]]+/gi;

// A bearer token with no preceding field name.
const BEARER_RE = /\bbearer\s+[^\s"',;)}\]]+/gi;

// Bare provider key literals, which appear in gateway messages with no field
// name at all.
const KEY_LITERAL_RE =
  /\b(?:sk|sk-ant|sk-or-v1|sk-proj|xai|gsk|pplx|r8|hf|ghp|github_pat)[-_][A-Za-z0-9_-]{12,}/gi;
const GOOGLE_KEY_RE = /\bAIza[A-Za-z0-9_-]{10,}/g;

/** Replace credential-shaped substrings in text that is about to be displayed. */
export function redactSecrets(text: string): string {
  if (!text) {
    return text;
  }
  return text
    .replace(SECRET_FIELD_RE, (_match, field: string, separator: string) =>
      [field, separator, REDACTED].join("")
    )
    .replace(BEARER_RE, `Bearer ${REDACTED}`)
    .replace(KEY_LITERAL_RE, REDACTED)
    .replace(GOOGLE_KEY_RE, REDACTED);
}

/* ── Bounded formatting ──────────────────────────────────────────── */

/** One line of the collapsed header: enough to recognise the call by. */
export const SUMMARY_CHARS = 180;
/** One argument value inside the collapsed header summary. */
export const SUMMARY_VALUE_CHARS = 60;
/** One argument value in the expanded body, before "show all". */
export const BODY_VALUE_CHARS = 2000;
/** A result body in the expanded card, before "show all". */
export const RESULT_PREVIEW_CHARS = 4000;
/**
 * Extra characters read past the requested limit so a credential straddling the
 * cut is matched by `redactSecrets` in full instead of surviving as a prefix.
 */
const REDACTION_SLACK_CHARS = 256;

export interface BoundedText {
  text: string;
  truncated: boolean;
}

/**
 * `JSON.stringify(value, null, 2)` that stops once `limit` characters have been
 * produced. This is the whole reason a 400 kB tool result costs the same to
 * summarise as a two-key one.
 */
export function stringifyBounded(value: JsonValue, limit: number): BoundedText {
  const parts: string[] = [];
  let used = 0;
  let truncated = false;

  function push(chunk: string): void {
    if (truncated) {
      return;
    }
    if (used + chunk.length >= limit) {
      parts.push(chunk.slice(0, Math.max(0, limit - used)));
      used = limit;
      truncated = true;
      return;
    }
    parts.push(chunk);
    used += chunk.length;
  }

  function walk(node: JsonValue, indent: string): void {
    if (truncated) {
      return;
    }
    if (node === null || typeof node !== "object") {
      // Slice long strings *before* quoting them so the quoting itself stays
      // proportional to the budget rather than to the payload.
      push(
        typeof node === "string" && node.length > limit
          ? JSON.stringify(node.slice(0, limit))
          : JSON.stringify(node)
      );
      return;
    }
    const inner = `${indent}  `;
    if (Array.isArray(node)) {
      if (node.length === 0) {
        push("[]");
        return;
      }
      push("[\n");
      for (let i = 0; i < node.length && !truncated; i += 1) {
        push(inner);
        walk(node[i], inner);
        push(i === node.length - 1 ? "\n" : ",\n");
      }
      push(`${indent}]`);
      return;
    }
    const keys = Object.keys(node);
    if (keys.length === 0) {
      push("{}");
      return;
    }
    push("{\n");
    for (let i = 0; i < keys.length && !truncated; i += 1) {
      push(`${inner}${JSON.stringify(keys[i])}: `);
      walk(node[keys[i]], inner);
      push(i === keys.length - 1 ? "\n" : ",\n");
    }
    push(`${indent}}`);
  }

  walk(value, "");
  return { text: parts.join(""), truncated };
}

/**
 * Display text for one JSON value, redacted and capped at `limit` characters.
 *
 * Strings are shown raw — a prompt or a skill body reads far better without JSON
 * quoting and `\n` escapes — and everything else is pretty-printed.
 */
export function boundedValueText(value: JsonValue, limit: number): BoundedText {
  const budget = limit + REDACTION_SLACK_CHARS;
  const raw: BoundedText =
    typeof value === "string"
      ? { text: value.slice(0, budget), truncated: value.length > budget }
      : stringifyBounded(value, budget);

  const redacted = redactSecrets(raw.text);
  if (redacted.length <= limit) {
    return { text: redacted, truncated: raw.truncated };
  }
  // Drop the token the cut landed inside, so half a credential cannot be shown
  // when the whole of it was past the redaction window.
  const clipped = redacted.slice(0, limit);
  const whole = clipped.replace(/\S+$/, "").trimEnd();
  return { text: whole || clipped, truncated: true };
}

/** Full, redacted display text for one JSON value. Call only when expanded. */
export function toolValueText(value: JsonValue): string {
  return redactSecrets(
    typeof value === "string" ? value : JSON.stringify(value, null, 2)
  );
}

/*
 * `redactSecrets` recognises a credential by the field name in front of it, so it
 * cannot fire on an argument whose name and value are displayed as two separate
 * pieces of text. An argument *called* `api_key` is exactly that case, so the
 * name is matched on its own and the value replaced wholesale.
 */
const SECRET_ARGUMENT_NAME_RE =
  /^(authorization|proxy[_-]?authorization|x[_-]?bf[_-]?api[_-]?key|x[_-]?api[_-]?key|x[_-]?goog[_-]?api[_-]?key|api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|id[_-]?token|auth[_-]?token|client[_-]?secret|secret|password|passwd|token|credentials?)$/i;

/** Whether an argument's own name says its value is a credential. */
export function isSecretArgumentName(name: string): boolean {
  return SECRET_ARGUMENT_NAME_RE.test(name.trim());
}

/** Bounded display text for one named argument. */
export function boundedArgumentText(
  name: string,
  value: JsonValue,
  limit: number
): BoundedText {
  if (isSecretArgumentName(name)) {
    return { text: REDACTED, truncated: false };
  }
  return boundedValueText(value, limit);
}

/** Full display text for one named argument. Call only when expanded. */
export function argumentText(name: string, value: JsonValue): string {
  return isSecretArgumentName(name) ? REDACTED : toolValueText(value);
}

/* ── Reading a tool exchange ─────────────────────────────────────── */

export interface ToolArgument {
  name: string;
  value: JsonValue;
}

export type ToolExchangeStatus = "pending" | "ok" | "error";

export interface ToolExchangeView {
  /** The name the model called, preferred over the server-side alias. */
  toolName: string;
  toolCallId: string;
  /** MCP assignment or server URL the call was routed to, when known. */
  server: string | null;
  /** Named arguments, in the order the payload lists them. */
  args: ToolArgument[];
  /**
   * Body to show when the call payload carries no `arguments` object — older
   * events and the invalid-tool-call path both produce one.
   */
  callFallback: string | null;
  status: ToolExchangeStatus;
  /** One bounded line describing the arguments, for the collapsed header. */
  summary: string;
  /** Size of the result text, so the header can hint at it without building it. */
  resultChars: number;
  /** A bounded first line of an error result, shown without expanding. */
  errorPreview: string | null;
}

function asString(value: JsonValue | undefined): string | null {
  return typeof value === "string" && value ? value : null;
}

function argumentsOf(payload: Record<string, JsonValue>): ToolArgument[] {
  const args = payload.arguments;
  if (!args || typeof args !== "object" || Array.isArray(args)) {
    return [];
  }
  return Object.keys(args).map((name) => ({ name, value: args[name] }));
}

/**
 * Content parts of a tool result payload, which the orchestrator always writes
 * as `{is_error, content: [{type: "text", text}]}`.
 */
function resultTextParts(payload: Record<string, JsonValue>): string[] {
  const result = payload.result;
  if (result && typeof result === "object" && !Array.isArray(result)) {
    const content = result.content;
    if (Array.isArray(content)) {
      const parts: string[] = [];
      for (const part of content) {
        if (typeof part === "string") {
          parts.push(part);
          continue;
        }
        if (part && typeof part === "object" && !Array.isArray(part)) {
          const text = part.text;
          if (typeof text === "string") {
            parts.push(text);
          }
        }
      }
      if (parts.length > 0) {
        return parts;
      }
    }
  }
  // Fall back to the same keys the generic event body uses, so an event shape
  // this function does not know still shows something.
  for (const key of ["text", "summary_text", "message"] as const) {
    const value = payload[key];
    if (typeof value === "string" && value) {
      return [value];
    }
  }
  return [];
}

/** Full, redacted text of a tool result. Call only when expanded. */
export function toolResultText(result: JobEventResponse): string {
  const parts = resultTextParts(result.payload);
  if (parts.length > 0) {
    return redactSecrets(parts.join("\n"));
  }
  return redactSecrets(JSON.stringify(result.payload, null, 2));
}

/**
 * Bounded, redacted text of a tool result — for headers and previews. Reads at
 * most `limit` characters out of the payload.
 */
export function boundedResultText(
  result: JobEventResponse,
  limit: number
): BoundedText {
  const parts = resultTextParts(result.payload);
  if (parts.length === 0) {
    return boundedValueText(result.payload, limit);
  }
  // Only as many parts as the budget needs.
  let joined = "";
  for (const part of parts) {
    joined = joined ? `${joined}\n${part}` : part;
    if (joined.length > limit + REDACTION_SLACK_CHARS) {
      break;
    }
  }
  return boundedValueText(joined, limit);
}

function resultCharCount(payload: Record<string, JsonValue>): number {
  return resultTextParts(payload).reduce(
    (total, part) => total + part.length,
    0
  );
}

function summarise(view: {
  args: ToolArgument[];
  callFallback: string | null;
}): string {
  if (view.args.length === 0) {
    return view.callFallback
      ? boundedValueText(view.callFallback, SUMMARY_CHARS).text
      : "";
  }
  const pieces: string[] = [];
  for (const arg of view.args) {
    if (pieces.join("  ·  ").length >= SUMMARY_CHARS) {
      break;
    }
    // Only scalars are worth reading inline; a nested object or list is shown
    // as its shape so the summary stays one glanceable line.
    if (arg.value !== null && typeof arg.value === "object") {
      pieces.push(
        `${arg.name}: ${Array.isArray(arg.value) ? `[${arg.value.length} items]` : "{…}"}`
      );
      continue;
    }
    const { text, truncated } = boundedArgumentText(
      arg.name,
      arg.value,
      SUMMARY_VALUE_CHARS
    );
    const oneLine = text.replace(/\s+/g, " ").trim();
    pieces.push(`${arg.name}: ${oneLine}${truncated ? "…" : ""}`);
  }
  return boundedValueText(pieces.join("  ·  "), SUMMARY_CHARS).text;
}

/**
 * Build everything a collapsed tool-exchange card renders. Cheap by
 * construction: no full payload is serialised here.
 */
export function buildToolExchangeView(
  call: JobEventResponse | null,
  result: JobEventResponse | null
): ToolExchangeView {
  const source = call ?? result;
  const payload = source?.payload ?? {};
  const toolName =
    asString(payload.exposed_tool_name) ??
    asString(payload.tool_name) ??
    source?.event_type ??
    "tool";
  const args = call ? argumentsOf(call.payload) : [];
  const callFallback =
    call && args.length === 0
      ? (asString(call.payload.text) ??
        asString(call.payload.summary_text) ??
        null)
      : null;

  const isError = result ? result.payload.is_error === true : false;
  const status: ToolExchangeStatus = !result
    ? "pending"
    : isError
      ? "error"
      : "ok";

  // `server_url` is an operator-registered MCP endpoint and some vendors put a
  // token in the path or query, so the provenance line is redacted like any
  // other displayed string. The tool name is redacted too: for an invalid tool
  // call it is whatever the model emitted.
  const server = asString(payload.assignment) ?? asString(payload.server_url);

  return {
    toolName: redactSecrets(toolName),
    toolCallId: asString(payload.tool_call_id) ?? "",
    server: server === null ? null : redactSecrets(server),
    args,
    callFallback,
    status,
    summary: summarise({ args, callFallback }),
    resultChars: result ? resultCharCount(result.payload) : 0,
    errorPreview:
      result && isError
        ? boundedResultText(result, SUMMARY_CHARS).text || null
        : null,
  };
}

/* ── System tools ────────────────────────────────────────────────── */

/**
 * The subagent a `spawn_subagent` / `prompt_player_agent` call launched, or a
 * `wait_for_subagent` call is waiting on — enough to open the existing subagent
 * output view on it.
 */
export interface SubagentReference {
  childJobId: string;
  name: string | null;
  playerId: string | null;
}

/** Job ids are orchestrator-generated identifiers, never paths or queries. */
const JOB_ID_RE = /^[A-Za-z0-9_-]{1,64}$/;

function parseJsonObject(text: string): Record<string, JsonValue> | null {
  try {
    const parsed: unknown = JSON.parse(text);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, JsonValue>;
    }
  } catch {
    /* not JSON — the handler returned prose, e.g. an error */
  }
  return null;
}

/**
 * Resolve the subagent an exchange refers to.
 *
 * A launch reports its child in the *result* (the handler returns
 * `{child_job_id, name}` as JSON), while a wait names its child in the
 * *arguments*, so both sides are consulted.
 */
export function subagentReference(
  call: JobEventResponse | null,
  result: JobEventResponse | null
): SubagentReference | null {
  let childJobId: string | null = null;
  let name: string | null = null;
  let playerId: string | null = null;

  if (call) {
    const args = call.payload.arguments;
    if (args && typeof args === "object" && !Array.isArray(args)) {
      childJobId = asString(args.child_job_id);
      playerId = asString(args.player_id);
    }
  }

  if (result && result.payload.is_error !== true) {
    // Bound the read: a well-formed launch result is a short JSON object, and a
    // long body is not one.
    const parts = boundedResultText(result, 2000);
    const parsed = parts.text.startsWith("{")
      ? parseJsonObject(parts.text)
      : null;
    if (parsed) {
      childJobId = asString(parsed.child_job_id) ?? childJobId;
      name = asString(parsed.name) ?? name;
      playerId = asString(parsed.player_id) ?? playerId;
    }
  }

  // `child_job_id` in a `wait_for_subagent` call is a raw model-written argument,
  // and the view this reference opens interpolates it into a request path. Only
  // something shaped like a job id is accepted, so a value carrying path or query
  // syntax cannot be turned into a request to somewhere else.
  if (!childJobId || !JOB_ID_RE.test(childJobId)) {
    return null;
  }
  return {
    childJobId,
    name: name === null ? null : redactSecrets(name),
    playerId: playerId === null ? null : redactSecrets(playerId),
  };
}

/**
 * How a tool is presented. `generic` is the readable default every tool gets;
 * the others are the system tools whose shape is known well enough to say
 * something better than "here are your arguments".
 */
export type ToolPresentation =
  | "generic"
  | "subagent_launch"
  | "subagent_wait"
  | "skill_load"
  | "user_question";

/**
 * Tool name → presentation. Adding a system tool here is the whole extension
 * point: the component module maps each presentation to a renderer and falls
 * back to the generic one for every tool absent from this table, so an MCP tool
 * nobody has thought about still renders readably.
 */
export const TOOL_PRESENTATIONS: Readonly<Record<string, ToolPresentation>> = {
  spawn_subagent: "subagent_launch",
  prompt_player_agent: "subagent_launch",
  wait_for_subagent: "subagent_wait",
  load_skill: "skill_load",
  load_skill_reference: "skill_load",
  ask_user: "user_question",
};

export function presentationForTool(toolName: string): ToolPresentation {
  return TOOL_PRESENTATIONS[toolName] ?? "generic";
}

/** Short, stable label for a job or session id in a header. */
export function shortId(id: string): string {
  return id.length > 8 ? `${id.slice(0, 8)}…` : id;
}
