import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom";

import { HistoryWorkspace } from "@/features/history/components/history-workspace";

// jsdom does not implement scrollIntoView; the transcript's scroll-lock uses it.
HTMLElement.prototype.scrollIntoView = vi.fn();

const listHistoryEvents = vi.fn();
// Flipped by the truncation test; the loader reports it through `isTruncated`.
let eventsTruncated = false;
const listHistorySnapshots = vi.fn();
const listHistoryGames = vi.fn();
const fetchDashboardConfig = vi.fn();
const listProviders = vi.fn();
const listAvailableSkills = vi.fn();
const listGames = vi.fn();
const listEvaluations = vi.fn();

vi.mock("@/features/history/lib/history-api", () => ({
  listHistoryEvents: (...args: unknown[]) => listHistoryEvents(...args),
  listAllHistoryTimeline: async (...args: unknown[]) => ({
    events: await listHistoryEvents(...args),
    truncated: eventsTruncated,
  }),
  fetchHistoryEvent: vi.fn(),
  listHistorySnapshots: (...args: unknown[]) => listHistorySnapshots(...args),
  listHistoryGames: (...args: unknown[]) => listHistoryGames(...args),
  restoreGame: vi.fn(),
  deleteHistoryGame: vi.fn(),
  deleteGameSession: vi.fn(),
  disposeReconstructionViaBeacon: vi.fn(),
}));

vi.mock("@/features/history/lib/eval-api", () => ({
  requestEvaluation: vi.fn(),
  cancelEvaluation: vi.fn(),
  listEvaluations: (...args: unknown[]) => listEvaluations(...args),
}));

vi.mock("@/features/play/lib/client-api", () => ({
  fetchDashboardConfig: (...args: unknown[]) => fetchDashboardConfig(...args),
  listProviders: (...args: unknown[]) => listProviders(...args),
  listAvailableSkills: (...args: unknown[]) => listAvailableSkills(...args),
  listSessions: () => Promise.resolve([]),
  listGames: (...args: unknown[]) => listGames(...args),
}));

const GAMES = [
  {
    game_id: "demo-001",
    event_count: 3,
    first_recorded_at: "2026-06-28T00:00:00Z",
    last_recorded_at: "2026-06-28T01:00:00Z",
  },
];

const EVENTS = [
  {
    seq: 1,
    event_id: "e1",
    game_id: "demo-001",
    actor: "agent",
    event_type: "move",
    payload: {
      intended_action: "Play Spider-Man",
      conversation_context: [{ role: "user", content: "your turn" }],
    },
    occurred_at: "2026-06-28T00:00:00Z",
    recorded_at: "2026-06-28T00:00:01Z",
  },
];

function stubSources() {
  fetchDashboardConfig.mockResolvedValue({
    defaultProviderId: "openrouter",
    defaultModelName: "m1",
    defaultReasoningEnabled: false,
    defaultReasoningEffort: "medium",
    defaultSkills: [],
    dragncardsFrontendUrl: "http://frontend.test",
    bifrostUiUrl: "http://localhost:4003",
  });
  listProviders.mockResolvedValue([]);
  listAvailableSkills.mockResolvedValue([]);
  listGames.mockResolvedValue([]);
  listHistorySnapshots.mockResolvedValue([]);
  listHistoryEvents.mockResolvedValue(EVENTS);
  listHistoryGames.mockResolvedValue(GAMES);
  listEvaluations.mockResolvedValue({ requests: [] });
}

afterEach(() => {
  vi.clearAllMocks();
  eventsTruncated = false;
});

describe("HistoryWorkspace responsive layout", () => {
  it("renders a games-list sidebar and an independently-scrollable transcript", async () => {
    stubSources();
    render(<HistoryWorkspace initialGameId="demo-001" />);

    // The two regions: games-list sidebar + transcript.
    const sidebar = await screen.findByTestId("history-sidebar");
    expect(sidebar).toBeInTheDocument();
    expect(
      within(sidebar).getByTestId("history-games-list")
    ).toBeInTheDocument();

    const transcript = await screen.findByTestId("history-transcript");
    // The transcript column scrolls independently.
    expect(transcript.className).toContain("overflow-y-auto");
    // Every event renders inline as a readable block.
    expect(
      within(transcript).getByTestId("history-event-1")
    ).toBeInTheDocument();
  });

  it("reveals per-event actions via the event's Actions toggle (restore + board)", async () => {
    stubSources();
    render(<HistoryWorkspace initialGameId="demo-001" />);

    // No action region until the event's Actions toggle is expanded.
    await screen.findByTestId("history-event-1");
    expect(
      screen.queryByTestId("history-event-actions-1")
    ).not.toBeInTheDocument();

    fireEvent.click(
      await screen.findByTestId("history-event-actions-toggle-1")
    );

    const actions = await screen.findByTestId("history-event-actions-1");
    expect(within(actions).getByTestId("restore-control")).toBeInTheDocument();
    expect(within(actions).getByTestId("board-control")).toBeInTheDocument();
    // Evaluation is NOT inline on the event — it is the header drawer only.
    expect(
      within(actions).queryByTestId("evaluation-control")
    ).not.toBeInTheDocument();
  });

  it("opens the game-level evaluation drawer from the header button", async () => {
    stubSources();
    render(<HistoryWorkspace initialGameId="demo-001" />);

    const openButton = await screen.findByTestId("history-evaluate-open");
    expect(screen.queryByTestId("evaluation-control")).not.toBeInTheDocument();

    fireEvent.click(openButton);

    const drawer = await screen.findByTestId("history-evaluate-drawer");
    expect(
      within(drawer).getByTestId("evaluation-control")
    ).toBeInTheDocument();
  });

  it("shows the Evaluations queue control with an active-count badge", async () => {
    stubSources();
    // Two requests, one active (a running target) and one fully terminal.
    listEvaluations.mockResolvedValue({
      requests: [
        {
          request_id: "req-1",
          game_id: "demo-001",
          status: "running",
          created_at: "2026-06-28T00:02:00Z",
          targets: [
            {
              target_seq: 1,
              scope: "move",
              round_span: null,
              status: "running",
            },
          ],
        },
        {
          request_id: "req-2",
          game_id: "demo-001",
          status: "completed",
          created_at: "2026-06-28T00:01:00Z",
          targets: [
            {
              target_seq: 2,
              scope: "move",
              round_span: null,
              status: "completed",
            },
          ],
        },
      ],
    });
    render(<HistoryWorkspace initialGameId="demo-001" />);

    // The queue control is always present, with a badge reflecting the one
    // active (non-terminal) request.
    expect(
      await screen.findByTestId("history-eval-queue-open")
    ).toBeInTheDocument();
    expect(
      await screen.findByTestId("history-eval-queue-badge")
    ).toHaveTextContent("1");

    // Opening it reveals the standing queue panel.
    fireEvent.click(screen.getByTestId("history-eval-queue-open"));
    expect(await screen.findByTestId("history-eval-queue")).toBeInTheDocument();
  });

  it("expands and collapses all event bodies from the toolbar", async () => {
    stubSources();
    render(<HistoryWorkspace initialGameId="demo-001" />);

    await screen.findByTestId("history-event-1");
    // Collapsed by default — no detail body.
    expect(
      screen.queryByTestId("history-detail-agent")
    ).not.toBeInTheDocument();

    fireEvent.click(await screen.findByTestId("history-expand-all"));
    expect(screen.getByTestId("history-detail-agent")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("history-collapse-all"));
    expect(
      screen.queryByTestId("history-detail-agent")
    ).not.toBeInTheDocument();
  });

  it("filters the transcript via the search input", async () => {
    stubSources();
    render(<HistoryWorkspace initialGameId="demo-001" />);

    await screen.findByTestId("history-event-1");
    const search = await screen.findByTestId("history-search");

    // A non-matching query empties the transcript with a no-matches state.
    fireEvent.change(search, { target: { value: "no-such-text-xyz" } });
    expect(screen.getByTestId("history-search-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("history-event-1")).not.toBeInTheDocument();

    // Clearing it restores the events.
    fireEvent.change(search, { target: { value: "" } });
    expect(
      screen.queryByTestId("history-search-empty")
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("history-event-1")).toBeInTheDocument();
  });

  it("renders a navigation tree whose move nodes select events", async () => {
    stubSources();
    render(<HistoryWorkspace initialGameId="demo-001" />);

    const tree = await screen.findByTestId("history-nav-tree");
    const move = within(tree).getByTestId("history-nav-move-1");
    fireEvent.click(move);
    // The clicked move becomes the selected event.
    expect(screen.getByTestId("history-event-1")).toHaveAttribute(
      "aria-current",
      "true"
    );
  });

  it("keeps the sidebar's content inside the sidebar box", async () => {
    stubSources();
    render(<HistoryWorkspace initialGameId="demo-001" />);

    const sidebar = await screen.findByTestId("history-sidebar");
    const gamesList = within(sidebar).getByTestId("history-games-list");
    const navTree = within(sidebar).getByTestId("history-nav-tree");

    // The games list and the navigation tree are siblings in the sidebar column,
    // so the list must FLEX into the space the tree leaves. Claiming the full
    // sidebar height (`h-full`) instead pushes the sidebar's content past the
    // sidebar box, which makes the overflow-hidden workspace row scrollable —
    // and any scroll-into-view then displaces the main panel (and the
    // reconstructed board, header and Close control included) off the viewport.
    expect(gamesList.parentElement).toBe(navTree.parentElement);
    expect(gamesList.className).toContain("flex-1");
    expect(gamesList.className).toContain("min-h-0");
    expect(gamesList.className).not.toContain("h-full");
  });

  it("guards against horizontal overflow at the layout root and transcript", async () => {
    stubSources();
    const { container } = render(<HistoryWorkspace initialGameId="demo-001" />);
    await screen.findByTestId("history-transcript");

    // The page root must not scroll horizontally.
    const root = container.firstElementChild as HTMLElement;
    expect(root.className).toContain("overflow-hidden");

    // The main panel constrains its width (`min-w-0`) so wide content scrolls
    // inside, not the page body.
    const main = container.querySelector("main") as HTMLElement;
    expect(main.className).toContain("min-w-0");
    expect(main.className).toContain("overflow-hidden");
  });

  it("says how many events it is showing when the timeline is truncated", async () => {
    stubSources();
    listHistoryGames.mockResolvedValue([{ ...GAMES[0], event_count: 4321 }]);
    eventsTruncated = true;
    render(<HistoryWorkspace initialGameId="demo-001" />);

    const notice = await screen.findByTestId("history-truncated-notice");
    // A bound that cuts the timeline must be disclosed against the true total,
    // never left looking complete.
    expect(notice).toHaveTextContent(
      `Showing the first ${EVENTS.length} of 4,321`
    );
  });

  it("shows no truncation notice when the whole timeline loaded", async () => {
    stubSources();
    render(<HistoryWorkspace initialGameId="demo-001" />);
    await screen.findByTestId("history-transcript");

    expect(
      screen.queryByTestId("history-truncated-notice")
    ).not.toBeInTheDocument();
  });

  it("offers a jump-to-round control alongside the transcript search", async () => {
    stubSources();
    // Two rounds of play so the control has somewhere to jump to. The state
    // events report `roundNumber` 0 and 1, i.e. rounds 1 and 2 as displayed.
    listHistoryEvents.mockResolvedValue([
      ...EVENTS,
      {
        seq: 2,
        event_id: "e2",
        game_id: "demo-001",
        actor: "game-service",
        event_type: "game_state",
        payload: { state: { game: { roundNumber: 0, stepId: "1.1" } } },
        occurred_at: "2026-06-28T00:00:02Z",
        recorded_at: "2026-06-28T00:00:03Z",
        payload_complete: false,
      },
      {
        seq: 3,
        event_id: "e3",
        game_id: "demo-001",
        actor: "game-service",
        event_type: "game_state",
        payload: { state: { game: { roundNumber: 1, stepId: "0.0" } } },
        occurred_at: "2026-06-28T00:00:04Z",
        recorded_at: "2026-06-28T00:00:05Z",
        payload_complete: false,
      },
    ]);
    render(<HistoryWorkspace initialGameId="demo-001" />);

    await screen.findByTestId("history-transcript");
    // Sits in the same toolbar row as the search field.
    const jump = screen.getByTestId("history-round-jump");
    const search = screen.getByTestId("history-search");
    expect(jump.closest("div")?.parentElement).toBe(search.parentElement);
  });
});
