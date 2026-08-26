import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

import {
  BoardActions,
  HistoryTranscript,
} from "@/features/history/components/history-transcript";
import { HistoryEvent } from "@/features/shared/lib/types";
import { TRANSCRIPT_WINDOW_SIZE } from "@/features/history/lib/transcript-window";

const fetchHistoryEvent = vi.fn();

vi.mock("@/features/history/lib/history-api", () => ({
  fetchHistoryEvent: (...args: unknown[]) => fetchHistoryEvent(...args),
}));

// jsdom does not implement scrollIntoView; the scroll-lock auto-follow uses it.
HTMLElement.prototype.scrollIntoView = vi.fn();

const board: BoardActions = {
  gameId: "g1",
  isOpening: false,
  error: null,
  isOpen: false,
  onOpen: vi.fn(),
};

/**
 * A timeline entry as the timeline endpoint serves it: no raw state bulk, no
 * conversation, and `payload_complete: false` to say so. The round advances every
 * 18 events so the fixture spans several rounds, matching how a real game reads.
 */
function timelineEntry(seq: number): HistoryEvent {
  return {
    seq,
    event_id: `e${seq}`,
    game_id: "g1",
    actor: "game-service",
    event_type: "game_state",
    payload: {
      status: "in progress",
      action_args: { type: "next_step" },
      state: { game: { roundNumber: Math.floor(seq / 18), stepId: "1.1" } },
    },
    occurred_at: "2026-06-24T10:00:00Z",
    recorded_at: "2026-06-24T10:00:01Z",
    payload_complete: false,
  };
}

const LONG_TIMELINE = Array.from({ length: 200 }, (_, i) =>
  timelineEntry(i + 1)
);

function renderTranscript(
  events: HistoryEvent[],
  selectedSeq: number | null = null,
  onSelect = vi.fn()
) {
  return render(
    <HistoryTranscript
      events={events}
      selectedSeq={selectedSeq}
      onSelect={onSelect}
      onRestore={vi.fn().mockResolvedValue({})}
      board={board}
    />
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("endless scroll over a long timeline", () => {
  it("renders only a window, anchored at the newest events", () => {
    renderTranscript(LONG_TIMELINE);

    // The last event is rendered; the first is not.
    expect(screen.getByTestId("history-event-200")).toBeInTheDocument();
    expect(screen.queryByTestId("history-event-1")).not.toBeInTheDocument();
    expect(
      screen.getAllByTestId(/^history-event-\d+$/).length
    ).toBeLessThanOrEqual(TRANSCRIPT_WINDOW_SIZE);
  });

  it("offers to load earlier events, but not later ones, at the tail", () => {
    renderTranscript(LONG_TIMELINE);

    expect(screen.getByTestId("history-load-older")).toBeInTheDocument();
    expect(screen.queryByTestId("history-load-newer")).not.toBeInTheDocument();
  });

  it("extends the window towards older events on demand", () => {
    renderTranscript(LONG_TIMELINE);
    const before = screen.getAllByTestId(/^history-event-\d+$/).length;

    fireEvent.click(screen.getByTestId("history-load-older"));

    expect(screen.getAllByTestId(/^history-event-\d+$/).length).toBeGreaterThan(
      before
    );
    // Still anchored at the newest event — growing older does not drop the tail.
    expect(screen.getByTestId("history-event-200")).toBeInTheDocument();
  });

  it("keeps growing until the whole timeline is reachable", () => {
    renderTranscript(LONG_TIMELINE);
    for (let i = 0; i < 20; i += 1) {
      const older = screen.queryByTestId("history-load-older");
      if (!older) break;
      fireEvent.click(older);
    }
    expect(screen.queryByTestId("history-load-older")).not.toBeInTheDocument();
    expect(screen.getByTestId("history-event-1")).toBeInTheDocument();
  });

  it("renders a short timeline whole, with no scroll sentinels", () => {
    renderTranscript(LONG_TIMELINE.slice(0, 5));

    expect(screen.getByTestId("history-event-1")).toBeInTheDocument();
    expect(screen.getByTestId("history-event-5")).toBeInTheDocument();
    expect(screen.queryByTestId("history-load-older")).not.toBeInTheDocument();
    expect(screen.queryByTestId("history-load-newer")).not.toBeInTheDocument();
  });
});

describe("jumping to a distant event", () => {
  it("moves the window so a selection outside it is rendered", () => {
    // seq 3 sits in the first round, far outside the tail window.
    renderTranscript(LONG_TIMELINE, 3);

    expect(screen.getByTestId("history-event-3")).toBeInTheDocument();
    // The window rebuilt around the target rather than spanning to the end.
    expect(screen.queryByTestId("history-event-200")).not.toBeInTheDocument();
    expect(screen.getByTestId("history-load-newer")).toBeInTheDocument();
  });

  it("offers a way back to the newest events from a jump", () => {
    renderTranscript(LONG_TIMELINE, 3);

    fireEvent.click(screen.getByTestId("history-jump-to-latest"));

    expect(screen.getByTestId("history-event-200")).toBeInTheDocument();
    expect(screen.queryByTestId("history-load-newer")).not.toBeInTheDocument();
  });

  it("follows a selection that moves to another distant event", () => {
    const { rerender } = renderTranscript(LONG_TIMELINE, 3);
    expect(screen.getByTestId("history-event-3")).toBeInTheDocument();

    rerender(
      <HistoryTranscript
        events={LONG_TIMELINE}
        selectedSeq={150}
        onSelect={vi.fn()}
        onRestore={vi.fn().mockResolvedValue({})}
        board={board}
      />
    );

    expect(screen.getByTestId("history-event-150")).toBeInTheDocument();
  });
});

describe("on-demand event detail", () => {
  it("fetches the full event only when a body is opened", async () => {
    fetchHistoryEvent.mockResolvedValue({
      ...timelineEntry(200),
      payload: {
        status: "in progress",
        state: { game: { roundNumber: 11, stepId: "1.1" }, deltas: [] },
      },
      payload_complete: true,
    });
    renderTranscript(LONG_TIMELINE);

    expect(fetchHistoryEvent).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("history-event-body-toggle-200"));

    await waitFor(() =>
      expect(fetchHistoryEvent).toHaveBeenCalledWith("g1", 200, "dragncards")
    );
    expect(
      await screen.findByTestId("history-detail-game")
    ).toBeInTheDocument();
  });

  it("does not re-fetch an event whose payload is already complete", () => {
    const complete = LONG_TIMELINE.map((event) => ({
      ...event,
      payload_complete: true,
    }));
    renderTranscript(complete);

    fireEvent.click(screen.getByTestId("history-event-body-toggle-200"));

    expect(fetchHistoryEvent).not.toHaveBeenCalled();
    expect(screen.getByTestId("history-detail-game")).toBeInTheDocument();
  });

  it("reports a failed detail fetch instead of showing an empty body", async () => {
    fetchHistoryEvent.mockRejectedValue(new Error("history is unreachable"));
    renderTranscript(LONG_TIMELINE);

    fireEvent.click(screen.getByTestId("history-event-body-toggle-200"));

    expect(
      await screen.findByTestId("history-detail-error-200")
    ).toHaveTextContent("history is unreachable");
  });
});
