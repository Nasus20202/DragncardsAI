import { HistoryEvent, JsonValue } from "@/features/shared/lib/types";

/** Format a 0–10 score as "N/10", or null when not a finite number. */
export function formatScore(value: number | null | undefined): string | null {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  const rounded = Math.round(value * 10) / 10;
  return `${rounded}/10`;
}

/** Turn a snake/kebab action id into a readable label ("move_card" → "Move card"). */
export function humanize(value: string): string {
  const spaced = value.replace(/[_-]+/g, " ").trim();
  return spaced ? spaced.charAt(0).toUpperCase() + spaced.slice(1) : value;
}

export function asRecord(
  value: JsonValue | undefined
): Record<string, JsonValue> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, JsonValue>)
    : null;
}

/** Collapse whitespace and truncate long text for a single-line label. */
export function truncateText(value: string, max = 120): string {
  const collapsed = value.replace(/\s+/g, " ").trim();
  return collapsed.length > max ? `${collapsed.slice(0, max - 1)}…` : collapsed;
}

/** A concise, human description of what an event did. */
export function actionLabel(event: HistoryEvent): string {
  if (event.actor === "user") {
    const prompt = event.payload.prompt;
    return typeof prompt === "string" && prompt.trim()
      ? truncateText(prompt)
      : "User prompt";
  }
  if (event.actor === "agent") {
    const intended = event.payload.intended_action;
    return typeof intended === "string" && intended
      ? humanize(intended)
      : "Agent decision";
  }
  const args = asRecord(event.payload.action_args);
  const type = args?.type;
  return typeof type === "string" && type ? humanize(type) : "Board update";
}

/** Round + step ("phase") for an event, inherited from the nearest game-state. */
export interface RoundMeta {
  /**
   * The 1-based round of play this event belongs to, or null while the game is
   * still being set up (see `metaFromGameState`).
   */
  round: number | null;
  step: string | null;
}

/**
 * The Marvel Champions step ids and the phase each one belongs to, mirroring
 * the plugin's `json/steps.json`. Step ids are dotted strings, and the major
 * digit is NOT the phase: `0.0` opens a round ("Beginning") while `0.1` closes
 * it ("End"), so the phase has to be looked up rather than derived.
 */
const STEP_PHASES: Record<string, string> = {
  "0.0": "Beginning",
  "1.1": "Player",
  "1.2": "Player",
  "2.1": "Villain",
  "2.2": "Villain",
  "2.3": "Villain",
  "2.4": "Villain",
  "2.5": "Villain",
  "0.1": "End",
};

/** The step's Marvel Champions phase; "Setup" before any step is known. */
export function phaseName(step: string | null): string {
  if (!step) return "Setup";
  return STEP_PHASES[step] ?? "Unknown";
}

/** The DragnCards step at which a game is set up, before the first round. */
const SETUP_STEP = "0.0";

/**
 * The round/step an observed game state represents.
 *
 * DragnCards' `roundNumber` counts *completed* rounds — it is 0 for the whole
 * first round of play and only increments as a round closes — so the round in
 * play is `roundNumber + 1`. Setup is the exception: it happens during the
 * Beginning step of round 0, before the first player phase, and is not part of
 * round 1. Step `0.0` recurs at the top of every later round, so the
 * `roundNumber === 0` conjunct is what keeps "setup" to the start of the game.
 */
function metaFromGameState(
  event: HistoryEvent,
  fallback: RoundMeta
): RoundMeta {
  const game = asRecord(asRecord(event.payload.state)?.game ?? undefined);
  if (!game) return fallback;
  const rawRound = game.roundNumber;
  const rawStep = game.stepId;
  const step = rawStep != null ? String(rawStep) : fallback.step;
  if (typeof rawRound !== "number") return { round: fallback.round, step };
  const isSetup = rawRound === 0 && step === SETUP_STEP;
  return { round: isSetup ? null : rawRound + 1, step };
}

export function roundKey(meta: RoundMeta): string {
  return !meta.round ? "setup" : `round-${meta.round}`;
}

export function roundHeading(meta: RoundMeta): string {
  return !meta.round ? "Setup" : `Round ${meta.round}`;
}

export function evaluatorModel(event: HistoryEvent): string | null {
  const model = event.payload.evaluator?.model;
  return typeof model === "string" && model ? model : null;
}

/**
 * A human scope label for an evaluator verdict, so a round/range/game-level
 * verdict does not read as if it graded one move. Uses the verdict's `scope`
 * and `round_span` ([from, to]) from its payload.
 */
export function verdictScopeLabel(verdict: HistoryEvent): string {
  const scope =
    typeof verdict.payload.scope === "string" ? verdict.payload.scope : "move";
  const span = verdict.payload.round_span;
  if (scope === "round") {
    if (Array.isArray(span) && span.length > 0) {
      const from = span[0];
      const to = span[span.length - 1];
      if (typeof from === "number") {
        return from === to || typeof to !== "number"
          ? `Round ${from}`
          : `Rounds ${from}–${to}`;
      }
    }
    return "Round";
  }
  if (scope === "range") {
    if (Array.isArray(span) && span.length >= 2) {
      const [from, to] = span;
      if (typeof from === "number" && typeof to === "number") {
        return `Range #${from}–#${to}`;
      }
    }
    return "Range";
  }
  if (scope === "game") return "Whole game";
  return "Move";
}

/**
 * The player a verdict pertains to (e.g. "player1"), or null when the verdict
 * is unattributed (legacy events without a `player`).
 */
export function verdictPlayer(verdict: HistoryEvent): string | null {
  const player = verdict.payload.player;
  return typeof player === "string" && player ? player : null;
}

/**
 * The hierarchy level of a verdict, used to visually distinguish per-player
 * round/game roll-ups from per-move verdicts in the sub-tree.
 */
export function verdictLevel(verdict: HistoryEvent): "move" | "round" | "game" {
  const scope =
    typeof verdict.payload.scope === "string" ? verdict.payload.scope : "move";
  if (scope === "game") return "game";
  if (scope === "round") return "round";
  return "move";
}

/** A single level's aggregate scores for one player on the scorecard. */
export interface PlayerLevelScores {
  /** The individual overall scores at this level (0–10), in event order. */
  scores: number[];
  /** Mean of `scores`, or null when there are none. */
  average: number | null;
}

/** One player's row on the per-player game scorecard. */
export interface PlayerScorecard {
  player: string;
  move: PlayerLevelScores;
  round: PlayerLevelScores;
  game: PlayerLevelScores;
}

function emptyLevel(): PlayerLevelScores {
  return { scores: [], average: null };
}

function withAverage(scores: number[]): PlayerLevelScores {
  if (scores.length === 0) return { scores, average: null };
  const sum = scores.reduce((total, value) => total + value, 0);
  return { scores, average: sum / scores.length };
}

/**
 * A per-player scorecard derived from the evaluation events: each player's
 * move/round/game overall scores side by side, so players can be compared.
 * Players are listed in first-seen order; only attributed verdicts (with a
 * `player`) contribute. Returns an empty array when there are no per-player
 * verdicts yet.
 */
export function buildPlayerScorecard(
  events: HistoryEvent[]
): PlayerScorecard[] {
  const byPlayer = new Map<
    string,
    { move: number[]; round: number[]; game: number[] }
  >();
  const order: string[] = [];
  for (const event of events) {
    if (event.actor !== "evaluator") continue;
    const player = verdictPlayer(event);
    if (!player) continue;
    const score = event.payload.overall_score;
    if (typeof score !== "number" || Number.isNaN(score)) continue;
    let entry = byPlayer.get(player);
    if (!entry) {
      entry = { move: [], round: [], game: [] };
      byPlayer.set(player, entry);
      order.push(player);
    }
    entry[verdictLevel(event)].push(score);
  }
  return order.map((player) => {
    const entry = byPlayer.get(player) ?? { move: [], round: [], game: [] };
    return {
      player,
      move: entry.move.length ? withAverage(entry.move) : emptyLevel(),
      round: entry.round.length ? withAverage(entry.round) : emptyLevel(),
      game: entry.game.length ? withAverage(entry.game) : emptyLevel(),
    };
  });
}

/**
 * Evaluator verdicts grouped under the event they grade (their `target_seq`).
 * Verdicts are never shown as their own rows — they hang off the graded move.
 */
export function groupEvalsByTarget(
  events: HistoryEvent[]
): Map<number, HistoryEvent[]> {
  const map = new Map<number, HistoryEvent[]>();
  for (const event of events) {
    if (event.actor !== "evaluator") continue;
    const target = event.payload.target_seq;
    if (typeof target !== "number") continue;
    const list = map.get(target) ?? [];
    list.push(event);
    map.set(target, list);
  }
  return map;
}

/** The non-evaluator events — the primary, displayable timeline/transcript. */
export function primaryEvents(events: HistoryEvent[]): HistoryEvent[] {
  return events.filter((event) => event.actor !== "evaluator");
}

/**
 * Round/phase per event: game-state events carry roundNumber/stepId; every
 * other event inherits the most recent one.
 *
 * A `game-service` event embeds the state *after* its action was applied, so it
 * is attributed to the round/step it acted **from** — the running state before
 * the update. That keeps the move that closes a round inside that round instead
 * of letting it open the next one. Every other actor (agent/user/evaluator) is
 * attributed the latest observed state, which is the state it was looking at.
 */
export function buildMetaBySeq(events: HistoryEvent[]): Map<number, RoundMeta> {
  const map = new Map<number, RoundMeta>();
  let current: RoundMeta = { round: null, step: null };
  let observed = false;
  for (const event of events) {
    if (event.actor === "game-service") {
      const next = metaFromGameState(event, current);
      // Before any state has been observed there is no "acted from" round. The
      // event's own state is then the best attribution available — a timeline
      // that begins mid-game (after a restore, or once early events age out)
      // must report the round it actually starts in, not "Setup".
      map.set(event.seq, observed ? current : next);
      current = next;
      observed = true;
    } else {
      map.set(event.seq, current);
    }
  }
  return map;
}

/**
 * The round heading (if any) to render before each primary event — emitted
 * only when the round key changes from the previous primary event. The label
 * marks the START of a numbered round ("Round N — start"); Setup keeps its
 * plain label since it is not a numbered round.
 */
export function buildHeadingBySeq(
  primary: HistoryEvent[],
  metaBySeq: Map<number, RoundMeta>
): Map<number, { key: string; label: string }> {
  const map = new Map<number, { key: string; label: string }>();
  let lastKey: string | null = null;
  for (const event of primary) {
    const meta = metaBySeq.get(event.seq) ?? { round: null, step: null };
    const key = roundKey(meta);
    if (key !== lastKey) {
      const heading = roundHeading(meta);
      map.set(event.seq, {
        key,
        label: meta.round ? `${heading} — start` : heading,
      });
      lastKey = key;
    }
  }
  return map;
}

/**
 * The end-of-round marker (if any) to render AFTER each primary event — emitted
 * on the last event of a numbered round, meaning the NEXT primary event belongs
 * to a different round. A round is only marked as ended when the timeline shows
 * it ending: the final round of an in-progress (or truncated) timeline gets no
 * marker, because nothing proves it finished. The leading Setup band never
 * produces an end marker, since it is not a numbered round.
 */
export function buildRoundEndBySeq(
  primary: HistoryEvent[],
  metaBySeq: Map<number, RoundMeta>
): Map<number, { key: string; label: string }> {
  const map = new Map<number, { key: string; label: string }>();
  for (let i = 0; i < primary.length; i += 1) {
    const meta = metaBySeq.get(primary[i].seq) ?? { round: null, step: null };
    if (!meta.round) continue;
    if (i + 1 >= primary.length) continue;
    const key = roundKey(meta);
    const nextMeta = metaBySeq.get(primary[i + 1].seq) ?? {
      round: null,
      step: null,
    };
    if (roundKey(nextMeta) !== key) {
      map.set(primary[i].seq, { key, label: `${roundHeading(meta)} — end` });
    }
  }
  return map;
}

/**
 * A lowercased search haystack for one event, spanning its action label, actor,
 * and the payload text a reviewer would search by (intended action, reasoning,
 * prompt, and the stringified arguments/state). Used by the transcript search.
 */
export function eventSearchText(event: HistoryEvent): string {
  const parts: string[] = [actionLabel(event), event.actor];
  const p = event.payload;
  const push = (value: JsonValue | undefined | null) => {
    if (value === null || value === undefined) return;
    parts.push(typeof value === "string" ? value : JSON.stringify(value));
  };
  push(p.intended_action);
  push(p.reasoning);
  push(p.prompt);
  push(p.arguments);
  push(p.state);
  return parts.join(" ").toLowerCase();
}

/** One move node in the navigation tree. */
export interface NavMove {
  seq: number;
  label: string;
}

/** One round node (game → rounds → moves) in the navigation tree. */
export interface NavRound {
  key: string;
  label: string;
  moves: NavMove[];
}

/**
 * The game → rounds → moves navigation tree, derived from the primary timeline
 * and its per-seq round meta. Rounds are listed in first-seen order; each round
 * lists its moves with a short "action label · #seq" label.
 */
export function buildNavTree(
  primary: HistoryEvent[],
  metaBySeq: Map<number, RoundMeta>
): NavRound[] {
  const rounds: NavRound[] = [];
  const byKey = new Map<string, NavRound>();
  for (const event of primary) {
    const meta = metaBySeq.get(event.seq) ?? { round: null, step: null };
    const key = roundKey(meta);
    let round = byKey.get(key);
    if (!round) {
      round = { key, label: roundHeading(meta), moves: [] };
      byKey.set(key, round);
      rounds.push(round);
    }
    round.moves.push({
      seq: event.seq,
      label: `${actionLabel(event)} · #${event.seq}`,
    });
  }
  return rounds;
}
