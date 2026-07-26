import type { ComponentProps } from "react";

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom";

import { EvaluationQueue } from "@/features/history/components/evaluation-queue";
import { EvaluationQueueRequest } from "@/features/shared/lib/types";

const REQUESTS: EvaluationQueueRequest[] = [
  {
    request_id: "req-a",
    game_id: "g1",
    status: "running",
    created_at: "2026-06-28T00:02:00Z",
    targets: [
      { target_seq: 12, scope: "move", round_span: null, status: "running" },
    ],
  },
  {
    request_id: "req-b",
    game_id: "g2",
    status: "completed",
    created_at: "2026-06-28T00:01:00Z",
    targets: [
      { target_seq: 0, scope: "game", round_span: null, status: "completed" },
      { target_seq: 1, scope: "game", round_span: null, status: "completed" },
    ],
  },
];

const GAME_NAMES = { g1: "Spider-Man vs Rhino", g2: "Captain Marvel solo" };

function renderQueue(
  overrides: Partial<ComponentProps<typeof EvaluationQueue>> = {}
) {
  const props = {
    requests: REQUESTS,
    gameNames: GAME_NAMES,
    isLoading: false,
    error: null,
    onCancel: vi.fn(),
    onClear: vi.fn(),
    onClearAll: vi.fn(),
    onClose: vi.fn(),
    ...overrides,
  };
  render(<EvaluationQueue {...props} />);
  return props;
}

describe("EvaluationQueue panel", () => {
  it("lists requests across games with friendly names and scope labels", () => {
    renderQueue();

    const rowA = screen.getByTestId("history-eval-queue-item-req-a");
    expect(within(rowA).getByText("Spider-Man vs Rhino")).toBeInTheDocument();
    expect(
      screen.getByTestId("history-eval-queue-scope-req-a")
    ).toHaveTextContent("Move #12");

    const rowB = screen.getByTestId("history-eval-queue-item-req-b");
    expect(within(rowB).getByText("Captain Marvel solo")).toBeInTheDocument();
    expect(
      screen.getByTestId("history-eval-queue-scope-req-b")
    ).toHaveTextContent("Whole game (2 moves)");
  });

  it("offers Cancel only on non-terminal requests", () => {
    const { onCancel } = renderQueue();

    // The active request has a cancel button; the completed one does not.
    expect(
      screen.getByTestId("history-eval-queue-cancel-req-a")
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("history-eval-queue-cancel-req-b")
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("history-eval-queue-cancel-req-a"));
    expect(onCancel).toHaveBeenCalledWith("g1", "req-a");
  });

  it("offers Clear only on terminal requests and calls onClear", () => {
    const { onClear } = renderQueue();

    // The terminal request has a Clear button; the running one does not.
    expect(
      screen.getByTestId("history-eval-queue-clear-req-b")
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("history-eval-queue-clear-req-a")
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("history-eval-queue-clear-req-b"));
    expect(onClear).toHaveBeenCalledWith("req-b");
  });

  it("Clear all triggers onClearAll when a terminal request exists", () => {
    const { onClearAll } = renderQueue();

    const clearAll = screen.getByTestId("history-eval-queue-clear-all");
    expect(clearAll).not.toBeDisabled();
    fireEvent.click(clearAll);
    expect(onClearAll).toHaveBeenCalledTimes(1);
  });

  it("disables Clear all when no request is terminal", () => {
    renderQueue({
      requests: [REQUESTS[0]], // only the running request
    });
    expect(screen.getByTestId("history-eval-queue-clear-all")).toBeDisabled();
  });

  it("shows the per-player fan-out of a cascade request", () => {
    renderQueue({
      requests: [
        {
          request_id: "req-c",
          game_id: "g1",
          status: "running",
          created_at: "2026-06-28T00:03:00Z",
          targets: [
            {
              target_seq: 5,
              scope: "move",
              round_span: null,
              player: "player1",
              status: "completed",
            },
            {
              target_seq: 6,
              scope: "round",
              round_span: [1, 1],
              player: "player1",
              status: "running",
            },
            {
              target_seq: 6,
              scope: "round",
              round_span: [1, 1],
              player: "player2",
              status: "pending",
            },
            {
              target_seq: 6,
              scope: "game",
              round_span: [1, 6],
              player: "player1",
              status: "pending",
            },
          ],
        },
      ],
    });

    const players = screen.getByTestId("history-eval-queue-players-req-c");
    expect(within(players).getByText("player1")).toBeInTheDocument();
    expect(within(players).getByText("player2")).toBeInTheDocument();
  });

  it("renders an empty state when there are no requests", () => {
    renderQueue({ requests: [], gameNames: {} });
    expect(screen.getByTestId("history-eval-queue-empty")).toBeInTheDocument();
  });

  it("falls back to the game id when no friendly name is known", () => {
    renderQueue({ gameNames: {} });
    const rowA = screen.getByTestId("history-eval-queue-item-req-a");
    expect(within(rowA).getByText("g1")).toBeInTheDocument();
  });
});
