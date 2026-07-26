import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

import { HistoryWorkspace } from "@/features/history/components/history-workspace";

// jsdom does not implement scrollIntoView; the transcript's scroll-lock uses it.
HTMLElement.prototype.scrollIntoView = vi.fn();

const listHistoryEvents = vi.fn();
const listHistorySnapshots = vi.fn();
const restoreGame = vi.fn();
const listHistoryGames = vi.fn();
const deleteHistoryGame = vi.fn();
const requestEvaluation = vi.fn();
const cancelEvaluation = vi.fn();
const listEvaluations = vi.fn().mockResolvedValue({ requests: [] });
const fetchDashboardConfig = vi.fn();
const listProviders = vi.fn();
const listAvailableSkills = vi.fn();

vi.mock("@/features/history/lib/history-api", () => ({
  listHistoryEvents: (...args: unknown[]) => listHistoryEvents(...args),
  listHistorySnapshots: (...args: unknown[]) => listHistorySnapshots(...args),
  restoreGame: (...args: unknown[]) => restoreGame(...args),
  listHistoryGames: (...args: unknown[]) => listHistoryGames(...args),
  deleteHistoryGame: (...args: unknown[]) => deleteHistoryGame(...args),
}));

vi.mock("@/features/history/lib/eval-api", () => ({
  requestEvaluation: (...args: unknown[]) => requestEvaluation(...args),
  cancelEvaluation: (...args: unknown[]) => cancelEvaluation(...args),
  listEvaluations: (...args: unknown[]) => listEvaluations(...args),
}));

vi.mock("@/features/play/lib/client-api", () => ({
  fetchDashboardConfig: (...args: unknown[]) => fetchDashboardConfig(...args),
  listProviders: (...args: unknown[]) => listProviders(...args),
  listAvailableSkills: (...args: unknown[]) => listAvailableSkills(...args),
  listSessions: () => Promise.resolve([]),
}));

const GAMES = [
  {
    game_id: "demo-eval-001",
    event_count: 8,
    first_recorded_at: "2026-06-28T00:00:00Z",
    last_recorded_at: "2026-06-28T01:00:00Z",
  },
  {
    game_id: "demo-eval-002",
    event_count: 3,
    first_recorded_at: "2026-06-27T00:00:00Z",
    last_recorded_at: "2026-06-27T01:00:00Z",
  },
];

afterEach(() => {
  vi.clearAllMocks();
});

function stubSources() {
  fetchDashboardConfig.mockResolvedValue({
    defaultProviderId: "openrouter",
    defaultModelName: "m1",
    defaultReasoningEnabled: false,
    defaultReasoningEffort: "medium",
    defaultSkills: [],
  });
  listProviders.mockResolvedValue([]);
  listAvailableSkills.mockResolvedValue([]);
  listHistorySnapshots.mockResolvedValue([]);
  listHistoryEvents.mockResolvedValue([]);
}

describe("HistoryWorkspace games list + delete", () => {
  it("renders the games list with id/event-count rows and auto-selects the first game", async () => {
    stubSources();
    listHistoryGames.mockResolvedValue(GAMES);

    render(<HistoryWorkspace />);

    const list = await screen.findByTestId("history-games-list");
    expect(list).toBeInTheDocument();

    const firstRow = await screen.findByTestId("history-game-demo-eval-001");
    expect(firstRow).toHaveTextContent("demo-eval-001");
    expect(firstRow).toHaveTextContent("8 events");
    // Auto-selects the first game.
    await waitFor(() =>
      expect(firstRow).toHaveAttribute("aria-current", "true")
    );
  });

  it("honours the ?game_id deep link", async () => {
    stubSources();
    listHistoryGames.mockResolvedValue(GAMES);

    render(<HistoryWorkspace initialGameId="demo-eval-002" />);

    const row = await screen.findByTestId("history-game-demo-eval-002");
    await waitFor(() => expect(row).toHaveAttribute("aria-current", "true"));
  });

  it("switches the active game when another row is selected", async () => {
    stubSources();
    listHistoryGames.mockResolvedValue(GAMES);

    render(<HistoryWorkspace initialGameId="demo-eval-001" />);

    fireEvent.click(await screen.findByTestId("history-game-demo-eval-002"));

    await waitFor(() =>
      expect(screen.getByTestId("history-game-demo-eval-002")).toHaveAttribute(
        "aria-current",
        "true"
      )
    );
  });

  it("opens the confirm dialog from a row delete affordance, then deletes", async () => {
    stubSources();
    listHistoryGames.mockResolvedValueOnce(GAMES).mockResolvedValue([GAMES[1]]);
    deleteHistoryGame.mockResolvedValue({
      game_id: "demo-eval-001",
      deleted_events: 8,
      deleted_snapshots: 1,
    });

    render(<HistoryWorkspace initialGameId="demo-eval-001" />);

    fireEvent.click(
      await screen.findByTestId("history-game-delete-demo-eval-001")
    );
    expect(screen.getByTestId("history-delete-dialog")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("history-delete-confirm"));

    await waitFor(() =>
      expect(deleteHistoryGame).toHaveBeenCalledWith("demo-eval-001")
    );
    await waitFor(() =>
      expect(
        screen.queryByTestId("history-delete-dialog")
      ).not.toBeInTheDocument()
    );
    // The deleted game is gone from the list.
    await waitFor(() =>
      expect(
        screen.queryByTestId("history-game-demo-eval-001")
      ).not.toBeInTheDocument()
    );
  });

  it("dismisses the delete dialog on cancel without deleting", async () => {
    stubSources();
    listHistoryGames.mockResolvedValue(GAMES);

    render(<HistoryWorkspace initialGameId="demo-eval-001" />);

    fireEvent.click(
      await screen.findByTestId("history-game-delete-demo-eval-001")
    );
    fireEvent.click(screen.getByTestId("history-delete-cancel"));

    await waitFor(() =>
      expect(
        screen.queryByTestId("history-delete-dialog")
      ).not.toBeInTheDocument()
    );
    expect(deleteHistoryGame).not.toHaveBeenCalled();
  });

  it("collapses the sidebar, hiding the per-row delete affordance", async () => {
    stubSources();
    listHistoryGames.mockResolvedValue(GAMES);

    render(<HistoryWorkspace initialGameId="demo-eval-001" />);

    await screen.findByTestId("history-game-demo-eval-001");
    fireEvent.click(screen.getByTestId("history-games-collapse"));

    await waitFor(() =>
      expect(
        screen.queryByTestId("history-game-delete-demo-eval-001")
      ).not.toBeInTheDocument()
    );
  });
});
