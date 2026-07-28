import { describe, expect, it } from "vitest";

import { EvaluationQueueRequest } from "@/features/shared/lib/types";
import {
  countActiveRequests,
  isRequestActive,
  progressLabel,
  requestErrors,
  requestScopeLabel,
} from "@/features/history/lib/eval-queue";

function req(
  partial: Partial<EvaluationQueueRequest> &
    Pick<EvaluationQueueRequest, "targets">
): EvaluationQueueRequest {
  return {
    request_id: "r",
    game_id: "g",
    status: "pending",
    created_at: "2026-06-28T00:00:00Z",
    ...partial,
  };
}

describe("eval-queue helpers", () => {
  it("labels a single move/round/range/game target", () => {
    expect(
      requestScopeLabel(
        req({ targets: [{ target_seq: 12, scope: "move", status: "running" }] })
      )
    ).toBe("Move #12");
    expect(
      requestScopeLabel(
        req({
          targets: [
            {
              target_seq: 1,
              scope: "round",
              round_span: [3, 3],
              status: "running",
            },
          ],
        })
      )
    ).toBe("Round 3");
    expect(
      requestScopeLabel(
        req({
          targets: [
            {
              target_seq: 1,
              scope: "range",
              round_span: [4, 9],
              status: "running",
            },
          ],
        })
      )
    ).toBe("Range #4–#9");
    expect(
      requestScopeLabel(
        req({ targets: [{ target_seq: 0, scope: "game", status: "running" }] })
      )
    ).toBe("Whole game");
  });

  it("summarizes a multi-target request", () => {
    expect(
      requestScopeLabel(
        req({
          targets: [
            { target_seq: 0, scope: "game", status: "running" },
            { target_seq: 1, scope: "game", status: "pending" },
            { target_seq: 2, scope: "game", status: "pending" },
          ],
        })
      )
    ).toBe("Whole game (3 moves)");
    expect(
      requestScopeLabel(
        req({
          targets: [
            { target_seq: 1, scope: "move", status: "running" },
            { target_seq: 2, scope: "move", status: "pending" },
          ],
        })
      )
    ).toBe("2 moves");
  });

  it("reports per-request progress and active counts", () => {
    const r = req({
      targets: [
        { target_seq: 1, scope: "move", status: "completed" },
        { target_seq: 2, scope: "move", status: "running" },
      ],
    });
    expect(progressLabel(r)).toBe("1/2 done");
    expect(isRequestActive(r)).toBe(true);

    const terminal = req({
      targets: [{ target_seq: 1, scope: "move", status: "completed" }],
    });
    expect(isRequestActive(terminal)).toBe(false);

    expect(countActiveRequests([r, terminal])).toBe(1);
  });

  it("collects failures, including ones on a still-running target", () => {
    const r = req({
      targets: [
        { target_seq: 1, scope: "move", status: "completed" },
        {
          target_seq: 2,
          scope: "move",
          status: "running",
          error: "judge attempt 1/3 failed: timed out",
        },
        {
          target_seq: 3,
          scope: "round",
          round_span: [1, 3],
          status: "failed",
          error: "judge failed after retry limit: no judge key",
        },
      ],
    });

    expect(requestErrors(r)).toEqual([
      {
        label: "Move #2",
        status: "running",
        detail: "judge attempt 1/3 failed: timed out",
      },
      {
        label: "Rounds 1\u20133",
        status: "failed",
        detail: "judge failed after retry limit: no judge key",
      },
    ]);
  });

  it("treats a deliberate skip and a cancellation as non-failures", () => {
    const r = req({
      targets: [
        {
          target_seq: 1,
          scope: "move",
          status: "skipped",
          error: "non-strategic action 'get_game_state': read-only",
        },
        {
          target_seq: 2,
          scope: "move",
          status: "cancelled",
          error: "cancelled by request",
        },
        { target_seq: 3, scope: "move", status: "failed", error: "   " },
        { target_seq: 4, scope: "move", status: "failed", error: null },
      ],
    });

    expect(requestErrors(r)).toEqual([]);
  });
});
