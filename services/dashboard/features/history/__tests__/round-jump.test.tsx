import "@testing-library/jest-dom";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { RoundJump } from "@/features/history/components/round-jump";
import { installResizeObserver } from "@/features/shared/__tests__/heroui-test-env";
import {
  buildMetaBySeq,
  buildNavTree,
  primaryEvents,
} from "@/features/history/lib/history-rounds";
import { HistoryEvent } from "@/features/shared/lib/types";

beforeAll(installResizeObserver);

/** A `game-service` entry carrying only the round meta a timeline entry has. */
function stateEvent(
  seq: number,
  roundNumber: number,
  stepId: string
): HistoryEvent {
  return {
    seq,
    event_id: `e${seq}`,
    game_id: "g1",
    actor: "game-service",
    event_type: "game_state",
    payload: {
      status: "in progress",
      state: { game: { roundNumber, stepId } },
    },
    occurred_at: "2026-06-24T10:00:00Z",
    recorded_at: "2026-06-24T10:00:01Z",
    payload_complete: false,
  };
}

/**
 * Setup, then the whole first round of play (`roundNumber` 0 — DragnCards counts
 * *completed* rounds), then the second. The event that closes a round carries the
 * next round's number, which is why the closing move at seq 4 reports 1.
 */
const EVENTS: HistoryEvent[] = [
  stateEvent(1, 0, "0.0"),
  stateEvent(2, 0, "1.1"),
  stateEvent(3, 0, "0.1"),
  stateEvent(4, 1, "0.0"),
  stateEvent(5, 1, "1.1"),
  stateEvent(6, 2, "0.0"),
];

const ROUNDS = buildNavTree(primaryEvents(EVENTS), buildMetaBySeq(EVENTS));

describe("RoundJump", () => {
  it("lists Setup and each round of play, using the display numbering", async () => {
    const user = userEvent.setup();
    render(<RoundJump rounds={ROUNDS} onJump={vi.fn()} />);

    await user.click(screen.getByTestId("history-round-jump"));

    await waitFor(() => expect(screen.getAllByRole("option").length).toBe(3));
    const labels = screen.getAllByRole("option").map((o) => o.textContent);
    // The first round of play is "Round 1", never "Setup".
    expect(labels).toEqual(["Setup", "Round 1", "Round 2"]);
  });

  it("jumps to the first move of the chosen round", async () => {
    const user = userEvent.setup();
    const onJump = vi.fn();
    render(<RoundJump rounds={ROUNDS} onJump={onJump} />);

    await user.click(screen.getByTestId("history-round-jump"));
    await user.click(await screen.findByTestId("history-round-jump-round-1"));

    // Round 1 opens at seq 3. Each event is attributed to the state it acted
    // *from*, so seq 2 — whose pre-action state was still setup — is the move
    // that left setup and belongs to the Setup band, while seq 4, which closes
    // round 1, stays inside round 1.
    expect(onJump).toHaveBeenCalledWith(3);
  });

  it("jumps again when the same round is chosen twice", async () => {
    // It is an action, not a stored setting: re-picking the round the transcript
    // is already showing has to re-jump rather than be swallowed as a no-op.
    const user = userEvent.setup();
    const onJump = vi.fn();
    render(<RoundJump rounds={ROUNDS} onJump={onJump} />);

    await user.click(screen.getByTestId("history-round-jump"));
    await user.click(await screen.findByTestId("history-round-jump-round-1"));
    await user.click(screen.getByTestId("history-round-jump"));
    await user.click(await screen.findByTestId("history-round-jump-round-1"));

    expect(onJump).toHaveBeenCalledTimes(2);
    expect(onJump).toHaveBeenNthCalledWith(2, 3);
  });

  it("jumps to the setup band", async () => {
    const user = userEvent.setup();
    const onJump = vi.fn();
    render(<RoundJump rounds={ROUNDS} onJump={onJump} />);

    await user.click(screen.getByTestId("history-round-jump"));
    await user.click(await screen.findByTestId("history-round-jump-setup"));

    expect(onJump).toHaveBeenCalledWith(1);
  });

  it("renders nothing when there are no rounds to jump to", () => {
    const { container } = render(<RoundJump rounds={[]} onJump={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("skips a round that has no moves", () => {
    const { container } = render(
      <RoundJump
        rounds={[{ key: "round-1", label: "Round 1", moves: [] }]}
        onJump={vi.fn()}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });
});
