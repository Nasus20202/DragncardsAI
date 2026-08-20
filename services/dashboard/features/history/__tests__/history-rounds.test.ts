import { describe, expect, it } from "vitest";

import { HistoryEvent } from "@/features/shared/lib/types";
import {
  buildHeadingBySeq,
  buildMetaBySeq,
  buildNavTree,
  buildRoundEndBySeq,
  phaseName,
  primaryEvents,
  verdictScopeLabel,
} from "@/features/history/lib/history-rounds";

/**
 * A `game-service` event, which carries the state AFTER its action was applied.
 * `roundNumber` is DragnCards' COMPLETED-round counter, so the round in play is
 * `roundNumber + 1`.
 */
function gameEvent(
  seq: number,
  roundNumber: number,
  stepId: string
): HistoryEvent {
  return {
    seq,
    event_id: `game-${seq}`,
    game_id: "game-1",
    actor: "game-service",
    event_type: "game_state",
    payload: {
      state: { game: { roundNumber, stepId } },
      action_args: { type: "next_step" },
    },
    occurred_at: "2026-07-28T10:00:00Z",
    recorded_at: "2026-07-28T10:00:00Z",
  } as unknown as HistoryEvent;
}

function agentEvent(seq: number): HistoryEvent {
  return {
    seq,
    event_id: `agent-${seq}`,
    game_id: "game-1",
    actor: "agent",
    event_type: "agent_move",
    payload: { intended_action: "next_step" },
    occurred_at: "2026-07-28T10:00:00Z",
    recorded_at: "2026-07-28T10:00:00Z",
  } as unknown as HistoryEvent;
}

function marvelEvent(
  seq: number,
  playRound: number,
  phase: string,
  phaseLabel = phase
): HistoryEvent {
  return {
    seq,
    event_id: `marvel-${seq}`,
    game_id: "game-1",
    platform: "marvel-lcg",
    actor: "game-service",
    event_type: "game_state",
    payload: {
      platform: "marvel-lcg",
      state: { playRound, phase, phaseLabel },
    },
    occurred_at: "2026-07-28T10:00:00Z",
    recorded_at: "2026-07-28T10:00:00Z",
  } as unknown as HistoryEvent;
}

/**
 * A trimmed replica of a real recorded game (history game
 * 35128894-0cad-4b53-b195-d74b7428fe2c): setup happens at round 0 / step 0.0,
 * the first round of play runs at roundNumber 0, and the `next_step` that wraps
 * 0.1 -> 0.0 is the move that CLOSES a round while reporting the next one.
 */
const RECORDED_GAME: HistoryEvent[] = [
  gameEvent(1, 0, "0.0"), // setup: set player count
  agentEvent(2),
  gameEvent(3, 0, "0.0"), // setup: load deck
  gameEvent(4, 0, "1.1"), // next_step OUT of setup, into round 1
  agentEvent(5),
  gameEvent(6, 0, "1.1"), // a round-1 move
  gameEvent(7, 0, "0.1"), // round 1 reaches its End step
  gameEvent(8, 1, "0.0"), // the move that CLOSES round 1 (reports round 2)
  agentEvent(9),
  gameEvent(10, 1, "1.1"), // round 2 play
  gameEvent(11, 2, "0.0"), // the move that CLOSES round 2 (reports round 3)
  gameEvent(12, 2, "1.1"), // round 3 play, still in progress
];

describe("phaseName", () => {
  it("maps every Marvel Champions step to the phase the plugin defines", () => {
    // Ground truth: external/dragncards-mc-plugin/json/steps.json
    expect(phaseName("0.0")).toBe("Beginning");
    expect(phaseName("1.1")).toBe("Player");
    expect(phaseName("1.2")).toBe("Player");
    expect(phaseName("2.1")).toBe("Villain");
    expect(phaseName("2.5")).toBe("Villain");
    expect(phaseName("0.1")).toBe("End");
  });

  it("names the end-of-round step 'End', not 'Beginning'", () => {
    // Step "0.1" is phaseId "End" in the plugin. Banding on the major digit
    // collapsed it onto "0" and mislabelled it "Beginning".
    expect(phaseName("0.1")).toBe("End");
  });

  it("treats a missing step as Setup", () => {
    expect(phaseName(null)).toBe("Setup");
  });
});

describe("buildMetaBySeq", () => {
  it("uses the neutral Marvel state contract without incrementing playRound", () => {
    const meta = buildMetaBySeq([
      marvelEvent(1, 0, "setup", "Resolve Mulligans"),
      marvelEvent(2, 1, "player", "Player 1 Turn"),
      agentEvent(3),
    ]);
    expect(meta.get(1)).toMatchObject({ round: null, phase: "Resolve Mulligans", platform: "marvel-lcg" });
    expect(meta.get(2)).toMatchObject({ round: null, platform: "marvel-lcg" });
    expect(meta.get(3)).toMatchObject({ round: 1, phase: "Player 1 Turn", platform: "marvel-lcg" });
    expect(meta.get(3)?.step).toBeNull();
  });

  it("numbers the round in play as roundNumber + 1", () => {
    const meta = buildMetaBySeq(RECORDED_GAME);
    // roundNumber 0 at a play step is the FIRST round of play, not Setup.
    expect(meta.get(6)?.round).toBe(1);
    // roundNumber 1 is the SECOND round of play.
    expect(meta.get(10)?.round).toBe(2);
    expect(meta.get(12)?.round).toBe(3);
  });

  it("keeps Setup for the beginning step of round 0 only", () => {
    const meta = buildMetaBySeq(RECORDED_GAME);
    expect(meta.get(1)?.round).toBeNull();
    expect(meta.get(2)?.round).toBeNull();
    expect(meta.get(3)?.round).toBeNull();
    // Step 0.0 recurs at the start of later rounds; that is NOT setup.
    expect(meta.get(8)?.round).not.toBeNull();
  });

  it("attributes a game-service event to the round it acted FROM", () => {
    const meta = buildMetaBySeq(RECORDED_GAME);
    // seq 8 reports round 2 but is the move that ended round 1, so it belongs
    // to round 1 -- it must not open round 2.
    expect(meta.get(8)?.round).toBe(1);
    expect(meta.get(11)?.round).toBe(2);
  });

  it("has non-game-service events inherit the latest observed state", () => {
    const meta = buildMetaBySeq(RECORDED_GAME);
    // seq 9 follows the round-1-closing move, so the agent now observes round 2.
    expect(meta.get(9)?.round).toBe(2);
  });
});

describe("round boundaries", () => {
  it("starts each round at its first move, not at the previous round's last", () => {
    const primary = primaryEvents(RECORDED_GAME);
    const meta = buildMetaBySeq(RECORDED_GAME);
    const headings = buildHeadingBySeq(primary, meta);
    expect(headings.get(1)?.label).toBe("Setup");
    // seq 4 is the next_step decided DURING setup that leaves it, so it belongs
    // to Setup; round 1 opens with the first move made inside round 1.
    expect(headings.get(4)).toBeUndefined();
    expect(headings.get(5)?.label).toBe("Round 1 — start");
    // seq 8 ENDS round 1; round 2 opens at seq 9.
    expect(headings.get(8)).toBeUndefined();
    expect(headings.get(9)?.label).toBe("Round 2 — start");
  });

  it("ends a round on the move that closes it", () => {
    const primary = primaryEvents(RECORDED_GAME);
    const meta = buildMetaBySeq(RECORDED_GAME);
    const ends = buildRoundEndBySeq(primary, meta);
    expect(ends.get(8)?.label).toBe("Round 1 — end");
    expect(ends.get(11)?.label).toBe("Round 2 — end");
  });

  it("does not claim the final, unfinished round has ended", () => {
    const primary = primaryEvents(RECORDED_GAME);
    const meta = buildMetaBySeq(RECORDED_GAME);
    const ends = buildRoundEndBySeq(primary, meta);
    // The timeline stops mid-round 3. A truncated or in-progress timeline must
    // not fabricate an end marker at the cut point.
    expect(ends.get(12)).toBeUndefined();
    expect([...ends.values()].map((end) => end.label)).toEqual([
      "Round 1 — end",
      "Round 2 — end",
    ]);
  });

  it("never emits an end marker for the Setup band", () => {
    const primary = primaryEvents(RECORDED_GAME);
    const meta = buildMetaBySeq(RECORDED_GAME);
    const ends = buildRoundEndBySeq(primary, meta);
    expect([...ends.keys()]).not.toContain(1);
    expect([...ends.keys()]).not.toContain(3);
  });
});

describe("buildNavTree", () => {
  it("groups moves under the correctly numbered round they were made in", () => {
    const primary = primaryEvents(RECORDED_GAME);
    const meta = buildMetaBySeq(RECORDED_GAME);
    const tree = buildNavTree(primary, meta);
    expect(tree.map((round) => round.label)).toEqual([
      "Setup",
      "Round 1",
      "Round 2",
      "Round 3",
    ]);
    expect(tree.map((round) => round.moves.map((move) => move.seq))).toEqual([
      [1, 2, 3, 4],
      [5, 6, 7, 8],
      [9, 10, 11],
      [12],
    ]);
  });
});

/**
 * An evaluator verdict event. `round_span` is the `[from_seq, to_seq]` SEQ span
 * the eval-service graded; `round_number` is the round of PLAY it is, and is the
 * only thing the label may be built from.
 */
function verdictEvent(
  seq: number,
  payload: Record<string, unknown>
): HistoryEvent {
  return {
    seq,
    event_id: `verdict-${seq}`,
    game_id: "game-1",
    actor: "evaluator",
    event_type: "evaluation",
    payload,
    occurred_at: "2026-07-28T10:00:00Z",
    recorded_at: "2026-07-28T10:00:00Z",
  } as unknown as HistoryEvent;
}

describe("verdictScopeLabel", () => {
  /**
   * The real rounds of history game 35128894-0cad-4b53-b195-d74b7428fe2c, as the
   * eval-service reports them from `GET /games/{id}/rounds`: round 1 = seqs 1-63,
   * round 2 = 64-103, round 3 = 104-124. A round verdict's `round_span` holds the
   * SEQS, so rendering its two elements as round numbers labelled round 1
   * "Rounds 1–63" (DRA-25).
   */
  it("labels a round verdict with its round of play, not its seq span", () => {
    const label = verdictScopeLabel(
      verdictEvent(64, {
        scope: "round",
        target_seq: 63,
        round_span: [1, 63],
        round_number: 1,
      })
    );
    expect(label).toBe("Round 1");
    expect(label).not.toBe("Rounds 1–63");
  });

  it("follows the round number rather than the span's first element", () => {
    // Round 2 spans seqs 64-103: neither element of the span is the round number,
    // so a label that happens to read "Round 1" for round 1 is not enough.
    expect(
      verdictScopeLabel(
        verdictEvent(104, {
          scope: "round",
          target_seq: 103,
          round_span: [64, 103],
          round_number: 2,
        })
      )
    ).toBe("Round 2");
  });

  it("names no round for a verdict that records none (eval-1)", () => {
    // Verdicts recorded before the round of play was written back — every `eval-1`
    // verdict among them, whose spans were shifted by one event at each boundary
    // (DRA-14) — carry only a seq span. The label states the scope and stops there
    // rather than resolving a superseded span to a round it did not grade.
    const label = verdictScopeLabel(
      verdictEvent(64, {
        scope: "round",
        target_seq: 62,
        round_span: [1, 62],
        evaluator: { evaluator_version: "eval-1" },
      })
    );
    expect(label).toBe("Round");
    expect(label).not.toContain("62");
  });

  it("ignores a round number that is not a positive whole round", () => {
    for (const round of [0, -1, 1.5, "2", null]) {
      expect(
        verdictScopeLabel(
          verdictEvent(64, {
            scope: "round",
            target_seq: 63,
            round_span: [1, 63],
            round_number: round,
          })
        )
      ).toBe("Round");
    }
  });

  it("labels move, range and game verdicts as before", () => {
    expect(
      verdictScopeLabel(verdictEvent(13, { scope: "move", target_seq: 12 }))
    ).toBe("Move");
    expect(
      verdictScopeLabel(
        verdictEvent(20, {
          scope: "range",
          target_seq: 18,
          round_span: [10, 18],
        })
      )
    ).toBe("Range #10–#18");
    expect(
      verdictScopeLabel(
        verdictEvent(125, {
          scope: "game",
          target_seq: 124,
          round_span: [1, 124],
        })
      )
    ).toBe("Whole game");
  });
});
