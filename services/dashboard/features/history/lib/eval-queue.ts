import {
  EvaluationQueueRequest,
  EvaluationQueueScope,
  EvaluationQueueTarget,
  EvaluationTargetStatus,
} from "@/features/shared/lib/types";

/** Target states past which no further work happens. */
const TERMINAL_TARGET_STATES: EvaluationTargetStatus[] = [
  "completed",
  "skipped",
  "failed",
  "cancelled",
];

export function isTargetTerminal(status: EvaluationTargetStatus): boolean {
  return TERMINAL_TARGET_STATES.includes(status);
}

/** A request is non-terminal (active) while it has at least one live target. */
export function isRequestActive(request: EvaluationQueueRequest): boolean {
  return request.targets.some((target) => !isTargetTerminal(target.status));
}

/** The number of requests with at least one non-terminal target. */
export function countActiveRequests(
  requests: EvaluationQueueRequest[]
): number {
  return requests.reduce(
    (count, request) => count + (isRequestActive(request) ? 1 : 0),
    0
  );
}

/** A request is terminal (clearable) when no target is still in flight. */
export function isRequestTerminal(request: EvaluationQueueRequest): boolean {
  return !isRequestActive(request);
}

/** The number of fully-terminal (clearable) requests. */
export function countTerminalRequests(
  requests: EvaluationQueueRequest[]
): number {
  return requests.reduce(
    (count, request) => count + (isRequestTerminal(request) ? 1 : 0),
    0
  );
}

/** "{done}/{total} done" across a request's targets. */
export function progressLabel(request: EvaluationQueueRequest): string {
  const total = request.targets.length;
  const done = request.targets.reduce(
    (count, target) => count + (isTargetTerminal(target.status) ? 1 : 0),
    0
  );
  return `${done}/${total} done`;
}

/**
 * A queue target's label. A queued target is identified by SEQUENCE — that is what
 * it is keyed by, and it exists before it has been graded — so every scope here
 * reads in seq notation: `Move #12`, `Round #64–#103`, `Range #10–#18`.
 *
 * `round_span` is a `[from_seq, to_seq]` pair of event sequences, NOT a round
 * range, and is never rendered as one: a round covering seqs 1–63 used to read
 * "Rounds 1–63" (DRA-25). The round OF PLAY is not available here — the
 * eval-service records it on the finished verdict, not on the bookkeeping row,
 * because a row is created before its round has been graded — so the label states
 * the span it actually holds instead of inventing a round number for it.
 */
function targetScopeLabel(target: EvaluationQueueTarget): string {
  const span = target.round_span;
  if (target.scope === "move") return `Move #${target.target_seq}`;
  if (target.scope === "round") {
    if (Array.isArray(span) && span.length >= 2) {
      const [from, to] = span;
      if (typeof from === "number" && typeof to === "number") {
        return from === to ? `Round #${from}` : `Round #${from}–#${to}`;
      }
    }
    return "Round";
  }
  if (target.scope === "range") {
    if (Array.isArray(span) && span.length >= 2) {
      const [from, to] = span;
      if (typeof from === "number" && typeof to === "number") {
        return `Range #${from}–#${to}`;
      }
    }
    return "Range";
  }
  return "Whole game";
}

const SCOPE_NOUN: Record<EvaluationQueueScope, string> = {
  move: "moves",
  round: "rounds",
  range: "ranges",
  game: "games",
};

/**
 * The distinct players a request's targets pertain to, in first-seen order, so
 * a cascade's per-player fan-out is visible on the queue row. Unattributed
 * (legacy) targets contribute no player.
 */
export function requestPlayers(request: EvaluationQueueRequest): string[] {
  const seen = new Set<string>();
  const players: string[] = [];
  for (const target of request.targets) {
    const player = target.player;
    if (typeof player === "string" && player && !seen.has(player)) {
      seen.add(player);
      players.push(player);
    }
  }
  return players;
}

/** One target's failure, ready to render on the queue row. */
export interface EvaluationQueueError {
  /** The target it happened on, e.g. "Move #12". */
  label: string;
  status: EvaluationTargetStatus;
  detail: string;
}

/**
 * The failures a request has hit so far, in target order.
 *
 * Includes errors on targets that are still `running` — the eval-service records
 * a failed judge attempt on the target row while it retries — so a problem shows
 * up during the run rather than only in the request's final status. A deliberate
 * `skipped` reason (a non-strategic action, which carries no decision to grade)
 * and `cancelled` bookkeeping are not failures and are left out.
 */
export function requestErrors(
  request: EvaluationQueueRequest
): EvaluationQueueError[] {
  const errors: EvaluationQueueError[] = [];
  for (const target of request.targets) {
    const detail = target.error;
    if (typeof detail !== "string" || detail.trim() === "") continue;
    if (target.status === "skipped" || target.status === "cancelled") continue;
    errors.push({
      label: targetScopeLabel(target),
      status: target.status,
      detail,
    });
  }
  return errors;
}

/**
 * A human scope label for a queued request. A single target reads as the target
 * itself ("Move #12" / "Round #64–#103" / "Whole game"); multiple targets summarize
 * ("Whole game (5 moves)" / "3 moves" / "Mixed (4)").
 */
export function requestScopeLabel(request: EvaluationQueueRequest): string {
  const targets = request.targets;
  if (targets.length === 0) return "No targets";
  if (targets.length === 1) return targetScopeLabel(targets[0]);

  const scopes = new Set(targets.map((target) => target.scope));
  if (scopes.size === 1) {
    const [scope] = scopes;
    if (scope === "game") return `Whole game (${targets.length} moves)`;
    return `${targets.length} ${SCOPE_NOUN[scope]}`;
  }
  return `Mixed (${targets.length})`;
}
