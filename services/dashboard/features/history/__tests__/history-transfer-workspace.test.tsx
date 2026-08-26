import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

import { HistoryWorkspace } from "@/features/history/components/history-workspace";

// jsdom does not implement scrollIntoView; the transcript's scroll-lock uses it.
HTMLElement.prototype.scrollIntoView = vi.fn();

const importHistoryBundle = vi.fn();
const listHistoryGames = vi.fn();

vi.mock("@/features/history/lib/history-api", () => ({
  listAllHistoryEvents: async () => ({ events: [], truncated: false }),
  listHistorySnapshots: async () => [],
  listHistoryGames: (...args: unknown[]) => listHistoryGames(...args),
  historyExportUrl: (gameId: string, mode = "full") =>
    `/api/proxy/history/games/${gameId}/export?mode=${mode}`,
  historyExportFilename: (gameId: string, mode = "full") =>
    `dragncards-history-${gameId}-${mode}.ndjson`,
  importHistoryBundle: (...args: unknown[]) => importHistoryBundle(...args),
  restoreGame: vi.fn(),
  deleteHistoryGame: vi.fn(),
  deleteGameSession: vi.fn(),
  disposeReconstructionViaBeacon: vi.fn(),
}));

vi.mock("@/features/history/lib/eval-api", () => ({
  requestEvaluation: vi.fn(),
  cancelEvaluation: vi.fn(),
  listEvaluations: async () => ({ requests: [] }),
}));

vi.mock("@/features/play/lib/client-api", () => ({
  fetchDashboardConfig: async () => ({ dragncardsFrontendUrl: "" }),
  listProviders: async () => [],
  listAvailableSkills: async () => [],
  listSessions: async () => [],
  listGames: async () => [],
}));

const GAMES = [
  {
    game_id: "demo-001",
    event_count: 0,
    first_recorded_at: "2026-07-28T00:00:00Z",
    last_recorded_at: "2026-07-28T01:00:00Z",
  },
];

afterEach(() => {
  vi.clearAllMocks();
});

/**
 * Pick a bundle and confirm the target dialog it opens, which is what actually
 * issues the import. The default target — an id the service mints — is left
 * alone here; which target a choice sends is covered in `history-transfer`.
 */
async function importBundle() {
  fireEvent.change(screen.getByTestId("history-import-input"), {
    target: {
      files: [new File(['{"kind":"header"}\n'], "g.ndjson")],
    },
  });
  fireEvent.click(await screen.findByTestId("history-import-confirm"));
}

describe("history workspace export/import wiring", () => {
  it("offers both controls in the header once a game is selected", async () => {
    listHistoryGames.mockResolvedValue(GAMES);
    render(<HistoryWorkspace initialGameId="demo-001" />);

    expect(await screen.findByTestId("history-export")).toBeInTheDocument();
    expect(screen.getByTestId("history-import")).toBeInTheDocument();
    expect(
      screen.queryByTestId("history-transfer-notice")
    ).not.toBeInTheDocument();
  });

  it("shows a successful import in the notice row and switches to the game", async () => {
    listHistoryGames.mockResolvedValue(GAMES);
    importHistoryBundle.mockResolvedValue({
      game_id: "demo-001",
      platform: "dragncards",
      source_game_id: "demo-001",
      imported_events: 4,
      imported_snapshots: 1,
      mode: "full",
      source_id_references: 0,
    });
    render(<HistoryWorkspace initialGameId={null} />);

    await screen.findByTestId("history-import");
    await importBundle();

    const notice = await screen.findByTestId("history-transfer-notice");
    expect(notice).toHaveTextContent(
      "Imported 4 events and 1 snapshots into demo-001 from a full bundle."
    );
    expect(notice).toHaveAttribute("role", "status");
  });

  it("shows a rejected import as an alert naming the offending line", async () => {
    listHistoryGames.mockResolvedValue(GAMES);
    importHistoryBundle.mockRejectedValue(
      new Error("line 3: unknown record kind 'mystery'")
    );
    render(<HistoryWorkspace initialGameId="demo-001" />);

    await screen.findByTestId("history-import");
    await importBundle();

    await waitFor(() => {
      const notice = screen.getByTestId("history-transfer-notice");
      expect(notice).toHaveTextContent("line 3: unknown record kind 'mystery'");
      expect(notice).toHaveAttribute("role", "alert");
    });
  });
});
