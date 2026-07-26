import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

import { HistoryWorkspace } from "@/features/history/components/history-workspace";
import { HistoryEvent } from "@/features/shared/lib/types";

// jsdom does not implement scrollIntoView; the transcript's scroll-lock uses it.
HTMLElement.prototype.scrollIntoView = vi.fn();

// Mock the data layer so the workspace renders a controlled timeline and the
// evaluation control + queue talk to a stubbed eval-service. This is a
// component-level integration test (jsdom + RTL), not a true Playwright e2e —
// the live app is driven separately via the Playwright MCP.

const listHistoryEvents = vi.fn();
const listHistorySnapshots = vi.fn();
const restoreGame = vi.fn();
const listHistoryGames = vi.fn();
const deleteHistoryGame = vi.fn();
const requestEvaluation = vi.fn();
const cancelEvaluation = vi.fn();
const listEvaluations = vi.fn();
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

const MOVE_EVENT: HistoryEvent = {
  seq: 12,
  event_id: "e12",
  game_id: "g1",
  actor: "agent",
  event_type: "move",
  payload: { intended_action: "play card", reasoning: "tempo" },
  occurred_at: "2026-06-28T00:00:00Z",
  recorded_at: "2026-06-28T00:00:00Z",
};

function stubSources() {
  listHistoryGames.mockResolvedValue([]);
  fetchDashboardConfig.mockResolvedValue({
    defaultProviderId: "openrouter",
    defaultModelName: "openrouter/free",
    defaultReasoningEnabled: false,
    defaultReasoningEffort: "medium",
    defaultSkills: [],
  });
  listProviders.mockResolvedValue([]);
  listAvailableSkills.mockResolvedValue([]);
  listHistorySnapshots.mockResolvedValue([]);
  listHistoryEvents.mockResolvedValue([MOVE_EVENT]);
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("evaluation flow on the history workspace", () => {
  it("enqueues a submitted request and shows it in the persistent queue", async () => {
    stubSources();
    // The queue is empty until the request is submitted, then it appears active.
    const QUEUED = {
      requests: [
        {
          request_id: "req-1",
          game_id: "g1",
          status: "pending",
          created_at: "2026-06-28T00:02:00Z",
          targets: [
            {
              target_seq: 12,
              scope: "move",
              round_span: null,
              status: "running",
            },
          ],
        },
      ],
    };
    listEvaluations
      .mockResolvedValueOnce({ requests: [] })
      .mockResolvedValue(QUEUED);
    requestEvaluation.mockResolvedValue({
      request_id: "req-1",
      game_id: "g1",
      scope: "move",
      created_count: 1,
      skipped_count: 0,
      targets: [
        { target_seq: 12, scope: "move", round_span: null, status: "pending" },
      ],
    });

    render(<HistoryWorkspace initialGameId="g1" />);

    // Select the move, open the Evaluate drawer, submit.
    fireEvent.click(await screen.findByTestId("history-event-12"));
    fireEvent.click(await screen.findByTestId("history-evaluate-open"));
    fireEvent.click(await screen.findByTestId("eval-submit"));

    await waitFor(() => {
      expect(requestEvaluation).toHaveBeenCalledWith("g1", {
        scope: "move",
        selection: { seqs: [12] },
        force: false,
        judge: { provider_id: "openrouter", model_name: "openrouter/free" },
      });
    });

    // Submitting surfaces the queue confirmation and auto-opens the queue.
    expect(await screen.findByTestId("eval-enqueued")).toBeInTheDocument();
    const queue = await screen.findByTestId("history-eval-queue");
    expect(queue).toBeInTheDocument();

    // The new request shows up with its scope label and an active status.
    expect(
      await screen.findByTestId("history-eval-queue-item-req-1")
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("history-eval-queue-scope-req-1")
    ).toHaveTextContent("Move #12");
  });

  it("keeps the request in the queue after the Evaluate drawer is closed", async () => {
    stubSources();
    listEvaluations.mockResolvedValue({
      requests: [
        {
          request_id: "req-1",
          game_id: "g1",
          status: "pending",
          created_at: "2026-06-28T00:02:00Z",
          targets: [
            {
              target_seq: 12,
              scope: "move",
              round_span: null,
              status: "running",
            },
          ],
        },
      ],
    });
    requestEvaluation.mockResolvedValue({
      request_id: "req-1",
      game_id: "g1",
      scope: "move",
      created_count: 1,
      skipped_count: 0,
      targets: [
        { target_seq: 12, scope: "move", round_span: null, status: "pending" },
      ],
    });

    render(<HistoryWorkspace initialGameId="g1" />);

    fireEvent.click(await screen.findByTestId("history-event-12"));
    fireEvent.click(await screen.findByTestId("history-evaluate-open"));
    fireEvent.click(await screen.findByTestId("eval-submit"));

    // Close the Evaluate drawer immediately after submitting.
    await screen.findByTestId("eval-enqueued");
    fireEvent.click(screen.getByTestId("history-evaluate-close"));
    await waitFor(() =>
      expect(
        screen.queryByTestId("history-evaluate-drawer")
      ).not.toBeInTheDocument()
    );

    // The request is NOT cancelled and remains visible + cancelable in the queue.
    expect(cancelEvaluation).not.toHaveBeenCalled();
    expect(
      await screen.findByTestId("history-eval-queue-item-req-1")
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("history-eval-queue-cancel-req-1")
    ).toBeInTheDocument();
  });

  it("cancels a request from the queue", async () => {
    stubSources();
    listEvaluations.mockResolvedValue({
      requests: [
        {
          request_id: "req-9",
          game_id: "g1",
          status: "running",
          created_at: "2026-06-28T00:02:00Z",
          targets: [
            {
              target_seq: 5,
              scope: "move",
              round_span: null,
              status: "running",
            },
          ],
        },
      ],
    });
    cancelEvaluation.mockResolvedValue({ request_id: "req-9", cancelled: 1 });

    render(<HistoryWorkspace initialGameId="g1" />);

    fireEvent.click(await screen.findByTestId("history-eval-queue-open"));
    fireEvent.click(
      await screen.findByTestId("history-eval-queue-cancel-req-9")
    );

    await waitFor(() =>
      expect(cancelEvaluation).toHaveBeenCalledWith("g1", "req-9")
    );
  });
});
