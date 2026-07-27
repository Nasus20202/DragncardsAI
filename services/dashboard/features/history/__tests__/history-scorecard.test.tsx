import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom";

import { HistoryScorecard } from "@/features/history/components/history-scorecard";
import { HistoryEvent } from "@/features/shared/lib/types";

function evaluator(
  seq: number,
  payload: HistoryEvent["payload"]
): HistoryEvent {
  return {
    seq,
    event_id: `v${seq}`,
    game_id: "g1",
    actor: "evaluator",
    event_type: "evaluation",
    payload,
    occurred_at: "2026-06-24T10:00:00Z",
    recorded_at: "2026-06-24T10:00:01Z",
  };
}

describe("HistoryScorecard", () => {
  it("shows a needs-evaluation empty state with no per-player verdicts", () => {
    render(<HistoryScorecard events={[]} onClose={vi.fn()} />);
    expect(screen.getByTestId("history-scorecard")).toBeInTheDocument();
    expect(screen.getByTestId("history-scorecard-empty")).toBeInTheDocument();
  });

  it("aggregates per-player move/round/game scores side by side", () => {
    const events: HistoryEvent[] = [
      evaluator(1, {
        scope: "move",
        target_seq: 1,
        player: "player1",
        overall_score: 8,
      }),
      evaluator(2, {
        scope: "move",
        target_seq: 2,
        player: "player1",
        overall_score: 6,
      }),
      evaluator(3, {
        scope: "round",
        target_seq: 2,
        round_span: [1, 1],
        player: "player1",
        overall_score: 7,
      }),
      evaluator(4, {
        scope: "game",
        target_seq: 2,
        round_span: [1, 2],
        player: "player1",
        overall_score: 9,
      }),
      evaluator(5, {
        scope: "move",
        target_seq: 3,
        player: "player2",
        overall_score: 4,
      }),
      // Legacy / unattributed verdict — must not appear as a player row.
      evaluator(6, { scope: "move", target_seq: 4, overall_score: 5 }),
    ];
    render(<HistoryScorecard events={events} onClose={vi.fn()} />);

    const p1 = screen.getByTestId("history-scorecard-player-player1");
    // Columns: player | move | round | game. The table is an ARIA grid, so the
    // player column (the row header) is a `rowheader` and the three score
    // columns are `gridcell`s.
    expect(within(p1).getByRole("rowheader")).toHaveTextContent("player1");
    const p1cells = within(p1).getAllByRole("gridcell");
    // Move average is (8 + 6) / 2 = 7; round is 7; game is 9.
    expect(p1cells[0]).toHaveTextContent("7/10");
    expect(p1cells[1]).toHaveTextContent("7/10");
    expect(p1cells[2]).toHaveTextContent("9/10");

    const p2 = screen.getByTestId("history-scorecard-player-player2");
    expect(within(p2).getByText("4/10")).toBeInTheDocument();

    // The unattributed verdict creates no extra player row.
    expect(screen.queryAllByTestId(/^history-scorecard-player-/)).toHaveLength(
      2
    );
  });
});
