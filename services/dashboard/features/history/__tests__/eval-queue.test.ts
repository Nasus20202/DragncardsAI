import { describe, expect, it } from "vitest";

import { EvaluationQueueRequest } from "@/features/shared/lib/types";
import {
  countActiveRequests,
  isRequestActive,
  progressLabel,
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
});
