import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom";

import { HistoryNavTree } from "@/features/history/components/history-nav-tree";
import { HistoryEvent } from "@/features/shared/lib/types";

const ROUND1_STATE: HistoryEvent = {
  seq: 1,
  event_id: "g1",
  game_id: "g1",
  actor: "game-service",
  event_type: "state_changed",
  payload: {
    status: "in progress",
    state: { game: { roundNumber: 0, stepId: "1.1" } },
  },
  occurred_at: "2026-06-24T10:00:00Z",
  recorded_at: "2026-06-24T10:00:01Z",
};

const ROUND1_AGENT: HistoryEvent = {
  seq: 2,
  event_id: "a2",
  game_id: "g1",
  actor: "agent",
  event_type: "move",
  payload: { intended_action: "play_card" },
  occurred_at: "2026-06-24T10:01:00Z",
  recorded_at: "2026-06-24T10:01:01Z",
};

const ROUND2_STATE: HistoryEvent = {
  seq: 3,
  event_id: "g3",
  game_id: "g1",
  actor: "game-service",
  event_type: "state_changed",
  payload: {
    status: "in progress",
    state: { game: { roundNumber: 1, stepId: "2.1" } },
  },
  occurred_at: "2026-06-24T10:02:00Z",
  recorded_at: "2026-06-24T10:02:01Z",
};

const ROUND2_AGENT: HistoryEvent = {
  seq: 4,
  event_id: "a4",
  game_id: "g1",
  actor: "agent",
  event_type: "move",
  payload: { intended_action: "next_step" },
  occurred_at: "2026-06-24T10:03:00Z",
  recorded_at: "2026-06-24T10:03:01Z",
};

describe("HistoryNavTree", () => {
  it("lists rounds and their moves", () => {
    render(
      <HistoryNavTree
        events={[ROUND1_STATE, ROUND1_AGENT, ROUND2_STATE, ROUND2_AGENT]}
        selectedSeq={null}
        onSelect={vi.fn()}
      />
    );

    const tree = screen.getByTestId("history-nav-tree");
    expect(
      within(tree).getByTestId("history-nav-round-round-1")
    ).toBeInTheDocument();
    expect(
      within(tree).getByTestId("history-nav-round-round-2")
    ).toBeInTheDocument();
    // Round 1 lists both of its moves.
    expect(within(tree).getByTestId("history-nav-move-1")).toBeInTheDocument();
    expect(within(tree).getByTestId("history-nav-move-2")).toBeInTheDocument();
    expect(within(tree).getByTestId("history-nav-move-3")).toBeInTheDocument();
  });

  it("selects a move when its node is clicked", () => {
    const onSelect = vi.fn();
    render(
      <HistoryNavTree
        events={[ROUND1_STATE, ROUND1_AGENT, ROUND2_STATE, ROUND2_AGENT]}
        selectedSeq={null}
        onSelect={onSelect}
      />
    );

    fireEvent.click(screen.getByTestId("history-nav-move-2"));
    expect(onSelect).toHaveBeenCalledWith(2);
  });

  it("renders nothing when there are no events", () => {
    const { container } = render(
      <HistoryNavTree events={[]} selectedSeq={null} onSelect={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });
});
