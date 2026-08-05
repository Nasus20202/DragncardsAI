import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom";

import { HistoryScorecard } from "@/features/history/components/history-scorecard";
import { scoreColors } from "@/features/history/lib/score-colors";
import { HistoryEvent } from "@/features/shared/lib/types";

/** The background colour of the score chip showing `label` (e.g. "7.4/10"). */
function chipBackground(label: string): string | undefined {
  const chip = screen.getByText(label).closest("[data-slot='chip']");
  return (chip as HTMLElement | null)?.style.backgroundColor;
}

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
    const p1cells = within(p1).getAllByRole("cell");
    // Columns: player | move | round | game.
    // Move average is (8 + 6) / 2 = 7; round is 7; game is 9.
    expect(p1cells[1]).toHaveTextContent("7/10");
    expect(p1cells[2]).toHaveTextContent("7/10");
    expect(p1cells[3]).toHaveTextContent("9/10");

    const p2 = screen.getByTestId("history-scorecard-player-player2");
    expect(within(p2).getByText("4/10")).toBeInTheDocument();

    // The unattributed verdict creates no extra player row.
    expect(screen.queryAllByTestId(/^history-scorecard-player-/)).toHaveLength(
      2
    );
    // A single evaluator version -> nothing to disclose.
    expect(
      screen.queryByTestId("history-scorecard-version-notice")
    ).not.toBeInTheDocument();
  });

  it("averages only the newest evaluator version and discloses what it left out", () => {
    // eval-1 graded a move with a small fixed neighbour window and no
    // multi-action-play instruction, so its scores are on a different scale.
    // Averaging the two together would produce a number describing neither.
    const events: HistoryEvent[] = [
      evaluator(1, {
        scope: "move",
        target_seq: 1,
        player: "player1",
        overall_score: 2,
        evaluator: { evaluator_version: "eval-1" },
      }),
      evaluator(2, {
        scope: "move",
        target_seq: 2,
        player: "player1",
        overall_score: 3,
        evaluator: { evaluator_version: "eval-1" },
      }),
      evaluator(3, {
        scope: "move",
        target_seq: 3,
        player: "player1",
        overall_score: 8,
        evaluator: { evaluator_version: "eval-2" },
      }),
    ];
    render(<HistoryScorecard events={events} onClose={vi.fn()} />);

    const p1 = screen.getByTestId("history-scorecard-player-player1");
    // Only the eval-2 verdict is averaged: 8, not (2 + 3 + 8) / 3.
    expect(within(p1).getByText("8/10")).toBeInTheDocument();
    const notice = screen.getByTestId("history-scorecard-version-notice");
    expect(notice).toHaveTextContent("2 verdicts");
    expect(notice).toHaveTextContent(/earlier evaluator version/i);
    expect(screen.getByTestId("history-scorecard")).toHaveTextContent(
      "Graded by eval-2."
    );
  });

  it("treats unversioned verdicts as their own group", () => {
    // A verdict with no recorded version is legacy; when the newest verdict has a
    // version, the unversioned ones are excluded rather than mixed in.
    const events: HistoryEvent[] = [
      evaluator(1, {
        scope: "move",
        target_seq: 1,
        player: "player1",
        overall_score: 1,
      }),
      evaluator(2, {
        scope: "move",
        target_seq: 2,
        player: "player1",
        overall_score: 9,
        evaluator: { evaluator_version: "eval-2" },
      }),
    ];
    render(<HistoryScorecard events={events} onClose={vi.fn()} />);

    const p1 = screen.getByTestId("history-scorecard-player-player1");
    expect(within(p1).getByText("9/10")).toBeInTheDocument();
    expect(
      screen.getByTestId("history-scorecard-version-notice")
    ).toHaveTextContent("1 verdict ");
  });

  it("colours each cell from its own average rather than always green", () => {
    const events: HistoryEvent[] = [
      evaluator(1, {
        scope: "move",
        target_seq: 1,
        player: "player1",
        overall_score: 2,
      }),
      evaluator(2, {
        scope: "move",
        target_seq: 2,
        player: "player2",
        overall_score: 9,
      }),
    ];
    render(<HistoryScorecard events={events} onClose={vi.fn()} />);

    const low = chipBackground("2/10");
    const high = chipBackground("9/10");
    expect(low).not.toBe(high);
    // Each cell carries the ramp colour for its own average.
    expect(low).toBe(scoreColors(2)?.background);
    expect(high).toBe(scoreColors(9)?.background);
  });

  it("distinguishes averages a tenth of a point apart", () => {
    // The scorecard shows a mean, so a banded colour scale would collapse these
    // two players onto one colour.
    const scores = (player: string, values: number[], offset: number) =>
      values.map((value, index) =>
        evaluator(offset + index, {
          scope: "move",
          target_seq: offset + index,
          player,
          overall_score: value,
        })
      );
    render(
      <HistoryScorecard
        events={[
          // 37 / 5 = 7.4
          ...scores("player1", [8, 7, 7, 7, 8], 1),
          // 38 / 5 = 7.6
          ...scores("player2", [8, 8, 7, 7, 8], 6),
        ]}
        onClose={vi.fn()}
      />
    );

    expect(chipBackground("7.4/10")).not.toBe(chipBackground("7.6/10"));
  });

  it("shows a dash rather than a coloured chip when a level has no verdict", () => {
    render(
      <HistoryScorecard
        events={[
          evaluator(1, {
            scope: "move",
            target_seq: 1,
            player: "player1",
            overall_score: 5,
          }),
        ]}
        onClose={vi.fn()}
      />
    );

    const cells = within(
      screen.getByTestId("history-scorecard-player-player1")
    ).getAllByRole("cell");
    // Round and game have no verdict: an em-dash, and no chip to colour.
    expect(cells[2]).toHaveTextContent("—");
    expect(cells[2].querySelector("[data-slot='chip']")).toBeNull();
    expect(cells[3]).toHaveTextContent("—");
    expect(cells[3].querySelector("[data-slot='chip']")).toBeNull();
  });
});
