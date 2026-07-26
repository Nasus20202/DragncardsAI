import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

import { EvaluationControl } from "@/features/history/components/evaluation-control";

const requestEvaluation = vi.fn();

vi.mock("@/features/history/lib/eval-api", () => ({
  requestEvaluation: (...args: unknown[]) => requestEvaluation(...args),
}));

afterEach(() => {
  vi.clearAllMocks();
});

describe("EvaluationControl", () => {
  it("disables submission when no game is selected", () => {
    render(<EvaluationControl gameId={null} selectedSeq={5} />);
    expect(screen.getByTestId("eval-submit")).toBeDisabled();
  });

  it("requires a selected event for the default 'selected' mode", async () => {
    render(<EvaluationControl gameId="g1" selectedSeq={null} />);

    fireEvent.click(screen.getByTestId("eval-submit"));

    expect(await screen.findByTestId("eval-error")).toHaveTextContent(
      /select a timeline event/i
    );
    expect(requestEvaluation).not.toHaveBeenCalled();
  });

  it("enqueues the selected event and surfaces the queue confirmation", async () => {
    requestEvaluation.mockResolvedValue({
      request_id: "req-1",
      game_id: "g1",
      scope: "move",
      created_count: 1,
      skipped_count: 0,
      targets: [
        {
          target_seq: 12,
          scope: "move",
          round_span: null,
          status: "pending",
        },
      ],
    });
    const onEnqueued = vi.fn();
    render(
      <EvaluationControl gameId="g1" selectedSeq={12} onEnqueued={onEnqueued} />
    );

    fireEvent.click(screen.getByTestId("eval-submit"));

    await waitFor(() => {
      expect(requestEvaluation).toHaveBeenCalledWith("g1", {
        scope: "move",
        selection: { seqs: [12] },
        force: false,
      });
    });
    // The request is enqueued; the drawer shows a brief confirmation and the
    // workspace is told to refresh/open the queue.
    expect(await screen.findByTestId("eval-enqueued")).toBeInTheDocument();
    await waitFor(() => expect(onEnqueued).toHaveBeenCalled());
  });

  it("validates a numeric seq range before submitting", async () => {
    render(<EvaluationControl gameId="g1" selectedSeq={null} />);

    fireEvent.click(screen.getByRole("radio", { name: /seq range/i }));
    fireEvent.change(screen.getByTestId("eval-from-seq"), {
      target: { value: "10" },
    });
    fireEvent.change(screen.getByTestId("eval-to-seq"), {
      target: { value: "5" },
    });
    fireEvent.click(screen.getByTestId("eval-submit"));

    expect(await screen.findByTestId("eval-error")).toHaveTextContent(
      /range start must not exceed/i
    );
    expect(requestEvaluation).not.toHaveBeenCalled();
  });

  it("submits a whole-game cascade with scope 'game'", async () => {
    requestEvaluation.mockResolvedValue({
      request_id: "req-g",
      game_id: "g1",
      scope: "game",
      created_count: 0,
      skipped_count: 0,
      targets: [],
    });
    render(<EvaluationControl gameId="g1" selectedSeq={3} />);

    // Choosing the whole-game cascade pins the target to the whole game and
    // surfaces a helper note that it auto-grades everything beneath.
    fireEvent.click(
      screen.getByRole("radio", { name: /whole game \(cascade\)/i })
    );
    expect(screen.getByTestId("eval-cascade-note")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("eval-submit"));

    await waitFor(() => {
      expect(requestEvaluation).toHaveBeenCalledWith("g1", {
        scope: "game",
        selection: { whole_game: true },
        force: false,
      });
    });
  });

  it("submits a whole-game request with the chosen scope and force flag", async () => {
    requestEvaluation.mockResolvedValue({
      request_id: "req-3",
      game_id: "g1",
      scope: "round",
      created_count: 0,
      skipped_count: 0,
      targets: [],
    });
    render(<EvaluationControl gameId="g1" selectedSeq={3} />);

    fireEvent.click(screen.getByRole("radio", { name: /^round$/i }));
    // The target-selection "Whole game" (mode), distinct from the new
    // "Whole game (cascade)" scope radio.
    fireEvent.click(screen.getByRole("radio", { name: "Whole game" }));
    fireEvent.click(screen.getByTestId("eval-force"));
    fireEvent.click(screen.getByTestId("eval-submit"));

    await waitFor(() => {
      expect(requestEvaluation).toHaveBeenCalledWith("g1", {
        scope: "round",
        selection: { whole_game: true },
        force: true,
      });
    });
  });
});
