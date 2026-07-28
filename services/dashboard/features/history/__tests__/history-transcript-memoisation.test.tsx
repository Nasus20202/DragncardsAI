import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render } from "@testing-library/react";

import { HistoryEvent } from "@/features/shared/lib/types";

/**
 * Counts how many event rows render. A played-out game's transcript runs to
 * thousands of events, and before the rows were memoised every one of them
 * re-rendered on each selection change, search keystroke and poll refresh. Every
 * row calls `actionLabel` exactly once, so wrapping it counts row renders.
 */
const rowRenders = vi.fn();
vi.mock("@/features/history/lib/history-rounds", async (importOriginal) => {
  const actual =
    await importOriginal<
      typeof import("@/features/history/lib/history-rounds")
    >();
  return {
    ...actual,
    actionLabel: (event: HistoryEvent) => {
      rowRenders();
      return actual.actionLabel(event);
    },
  };
});

const { HistoryTranscript } =
  await import("@/features/history/components/history-transcript");

function makeEvents(count: number): HistoryEvent[] {
  return Array.from({ length: count }, (_, i) => ({
    seq: i + 1,
    event_id: `e-${i}`,
    game_id: "game-1",
    actor: (i % 2 === 0 ? "agent" : "game-service") as HistoryEvent["actor"],
    event_type: i % 2 === 0 ? "agent.move" : "game.state",
    payload: {
      intended_action: "move_card",
      status: "ok",
    } as HistoryEvent["payload"],
    occurred_at: new Date(1_700_000_000_000 + i * 1000).toISOString(),
    recorded_at: new Date(1_700_000_000_000 + i * 1000).toISOString(),
  }));
}

const board = {
  gameId: "game-1",
  isOpening: false,
  error: null,
  isOpen: false,
  onOpen: vi.fn(),
};
const onRestore = vi.fn();
const onSelect = vi.fn();

function transcript(events: HistoryEvent[], selectedSeq: number | null) {
  return (
    <HistoryTranscript
      events={events}
      selectedSeq={selectedSeq}
      onSelect={onSelect}
      onRestore={onRestore}
      board={board}
    />
  );
}

describe("HistoryTranscript re-render cost", () => {
  beforeEach(() => {
    rowRenders.mockClear();
    HTMLElement.prototype.scrollTo = vi.fn();
    HTMLElement.prototype.scrollIntoView = vi.fn();
  });

  it("re-renders only the rows whose selection changed", () => {
    const events = makeEvents(6);

    let rerender: (ui: React.ReactElement) => void = () => {};
    act(() => {
      rerender = render(transcript(events, null)).rerender;
    });
    expect(rowRenders).toHaveBeenCalledTimes(6);

    // Selecting the third event must touch that row only.
    rowRenders.mockClear();
    act(() => {
      rerender(transcript(events, 3));
    });
    expect(rowRenders).toHaveBeenCalledTimes(1);

    // Moving the selection touches the row losing it and the row gaining it.
    rowRenders.mockClear();
    act(() => {
      rerender(transcript(events, 4));
    });
    expect(rowRenders).toHaveBeenCalledTimes(2);
  });

  it("keeps every row out of the render when nothing changed", () => {
    const events = makeEvents(6);

    let rerender: (ui: React.ReactElement) => void = () => {};
    act(() => {
      rerender = render(transcript(events, 2)).rerender;
    });

    rowRenders.mockClear();
    act(() => {
      rerender(transcript(events, 2));
    });
    expect(rowRenders).not.toHaveBeenCalled();
  });
});
