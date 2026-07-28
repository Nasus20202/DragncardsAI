import { act, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useHistory } from "@/features/history/lib/use-history";
import { HistoryEvent } from "@/features/shared/lib/types";

const listAllHistoryTimeline = vi.fn();
const listHistorySnapshots = vi.fn();

vi.mock("@/features/history/lib/history-api", () => ({
  listAllHistoryTimeline: (...args: unknown[]) =>
    listAllHistoryTimeline(...args),
  listHistorySnapshots: (...args: unknown[]) => listHistorySnapshots(...args),
}));

function entry(seq: number): HistoryEvent {
  return {
    seq,
    event_id: `e${seq}`,
    game_id: "g1",
    actor: "game-service",
    event_type: "game_state",
    payload: { status: "in progress" },
    occurred_at: "2026-06-24T10:00:00Z",
    recorded_at: "2026-06-24T10:00:01Z",
    payload_complete: false,
  };
}

/** A probe that renders the hook's seqs and exposes its two refresh paths. */
function Probe({ gameId }: { gameId: string | null }) {
  const history = useHistory(gameId);
  return (
    <div>
      <span data-testid="seqs">
        {history.events.map((event) => event.seq).join(",")}
      </span>
      <span data-testid="truncated">{String(history.isTruncated)}</span>
      <span data-testid="error">{history.error ?? ""}</span>
      <button type="button" data-testid="refresh" onClick={history.refresh}>
        refresh
      </button>
      <button type="button" data-testid="reload" onClick={history.reload}>
        reload
      </button>
    </div>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listHistorySnapshots.mockResolvedValue([]);
});

describe("useHistory", () => {
  it("loads a game's timeline in ascending seq", async () => {
    listAllHistoryTimeline.mockResolvedValue({
      events: [entry(3), entry(1), entry(2)],
      truncated: false,
    });
    render(<Probe gameId="g1" />);

    await waitFor(() =>
      expect(screen.getByTestId("seqs")).toHaveTextContent("1,2,3")
    );
    expect(listAllHistoryTimeline).toHaveBeenCalledWith("g1");
  });

  it("reads only what is new on a refresh, and appends it", async () => {
    listAllHistoryTimeline.mockResolvedValueOnce({
      events: [entry(1), entry(2)],
      truncated: false,
    });
    render(<Probe gameId="g1" />);
    await waitFor(() =>
      expect(screen.getByTestId("seqs")).toHaveTextContent("1,2")
    );

    listAllHistoryTimeline.mockResolvedValueOnce({
      events: [entry(3)],
      truncated: false,
    });
    act(() => screen.getByTestId("refresh").click());

    await waitFor(() =>
      expect(screen.getByTestId("seqs")).toHaveTextContent("1,2,3")
    );
    // The whole point: the refresh resumed from the highest loaded seq rather
    // than re-reading the game.
    expect(listAllHistoryTimeline).toHaveBeenLastCalledWith("g1", {
      afterSeq: 2,
    });
  });

  it("advances the resume point across successive refreshes", async () => {
    listAllHistoryTimeline.mockResolvedValueOnce({
      events: [entry(1)],
      truncated: false,
    });
    render(<Probe gameId="g1" />);
    await waitFor(() =>
      expect(screen.getByTestId("seqs")).toHaveTextContent("1")
    );

    listAllHistoryTimeline.mockResolvedValueOnce({
      events: [entry(2)],
      truncated: false,
    });
    act(() => screen.getByTestId("refresh").click());
    await waitFor(() =>
      expect(screen.getByTestId("seqs")).toHaveTextContent("1,2")
    );

    listAllHistoryTimeline.mockResolvedValueOnce({
      events: [entry(3)],
      truncated: false,
    });
    act(() => screen.getByTestId("refresh").click());
    await waitFor(() =>
      expect(screen.getByTestId("seqs")).toHaveTextContent("1,2,3")
    );

    expect(listAllHistoryTimeline).toHaveBeenLastCalledWith("g1", {
      afterSeq: 2,
    });
  });

  it("does not duplicate an event a refresh returns twice", async () => {
    listAllHistoryTimeline.mockResolvedValueOnce({
      events: [entry(1), entry(2)],
      truncated: false,
    });
    render(<Probe gameId="g1" />);
    await waitFor(() =>
      expect(screen.getByTestId("seqs")).toHaveTextContent("1,2")
    );

    listAllHistoryTimeline.mockResolvedValueOnce({
      events: [entry(2), entry(3)],
      truncated: false,
    });
    act(() => screen.getByTestId("refresh").click());

    await waitFor(() =>
      expect(screen.getByTestId("seqs")).toHaveTextContent("1,2,3")
    );
  });

  it("re-reads the whole timeline on a reload", async () => {
    listAllHistoryTimeline.mockResolvedValue({
      events: [entry(1)],
      truncated: false,
    });
    render(<Probe gameId="g1" />);
    await waitFor(() =>
      expect(screen.getByTestId("seqs")).toHaveTextContent("1")
    );

    act(() => screen.getByTestId("reload").click());

    await waitFor(() =>
      expect(listAllHistoryTimeline).toHaveBeenCalledTimes(2)
    );
    // A reload takes no cursor: it starts over.
    expect(listAllHistoryTimeline).toHaveBeenLastCalledWith("g1");
  });

  it("keeps the loaded timeline when a background refresh fails", async () => {
    listAllHistoryTimeline.mockResolvedValueOnce({
      events: [entry(1), entry(2)],
      truncated: false,
    });
    render(<Probe gameId="g1" />);
    await waitFor(() =>
      expect(screen.getByTestId("seqs")).toHaveTextContent("1,2")
    );

    listAllHistoryTimeline.mockRejectedValueOnce(new Error("unreachable"));
    act(() => screen.getByTestId("refresh").click());

    await waitFor(() =>
      expect(listAllHistoryTimeline).toHaveBeenCalledTimes(2)
    );
    expect(screen.getByTestId("seqs")).toHaveTextContent("1,2");
    expect(screen.getByTestId("error")).toHaveTextContent("");
  });

  it("reports the truncation the walk hit", async () => {
    listAllHistoryTimeline.mockResolvedValue({
      events: [entry(1)],
      truncated: true,
    });
    render(<Probe gameId="g1" />);

    await waitFor(() =>
      expect(screen.getByTestId("truncated")).toHaveTextContent("true")
    );
  });

  it("clears everything and reads nothing without a game", async () => {
    render(<Probe gameId={null} />);

    await waitFor(() =>
      expect(screen.getByTestId("seqs")).toHaveTextContent("")
    );
    expect(listAllHistoryTimeline).not.toHaveBeenCalled();
  });

  it("surfaces a failed initial load", async () => {
    listAllHistoryTimeline.mockRejectedValue(new Error("history is down"));
    render(<Probe gameId="g1" />);

    await waitFor(() =>
      expect(screen.getByTestId("error")).toHaveTextContent("history is down")
    );
  });
});
