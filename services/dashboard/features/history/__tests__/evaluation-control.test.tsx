import { afterEach, describe, expect, it, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";

import { EvaluationControl } from "@/features/history/components/evaluation-control";
import { EvaluationRound } from "@/features/shared/lib/types";

const requestEvaluation = vi.fn();
const listGameRounds = vi.fn();

vi.mock("@/features/history/lib/eval-api", () => ({
  requestEvaluation: (...args: unknown[]) => requestEvaluation(...args),
  listGameRounds: (...args: unknown[]) => listGameRounds(...args),
}));

/**
 * Two rounds as the eval-service reports them. `round_number` is the 1-based
 * round OF PLAY — the eval-service has already converted DragnCards' raw
 * counter, which counts *completed* rounds — and is exactly what
 * `selection.rounds` accepts.
 */
const ROUNDS: EvaluationRound[] = [
  {
    round_number: 1,
    label: "Round 1",
    from_seq: 1,
    to_seq: 30,
    move_count: 12,
    players: ["player1"],
  },
  {
    round_number: 2,
    label: "Round 2",
    from_seq: 31,
    to_seq: 55,
    move_count: 9,
    players: ["player1"],
  },
];

afterEach(() => {
  vi.clearAllMocks();
});

/**
 * Activate a HeroUI control inside the row carrying a test id. The rows render
 * ARIA widgets (`checkbox`, `switch`) that respond to pointer events, so they are
 * driven through `userEvent` and their role, matching the judge-config tests.
 */
async function activate(
  user: ReturnType<typeof userEvent.setup>,
  testId: string,
  role: "checkbox" | "switch"
) {
  await user.click(within(screen.getByTestId(testId)).getByRole(role));
}

/** Renders the panel and waits for the round listing to settle. */
async function renderControl(props: {
  gameId: string | null;
  selectedSeq: number | null;
  onEnqueued?: () => void;
  rounds?: EvaluationRound[];
  roundsError?: Error;
}) {
  if (props.roundsError) {
    listGameRounds.mockRejectedValue(props.roundsError);
  } else {
    listGameRounds.mockResolvedValue(props.rounds ?? ROUNDS);
  }
  render(
    <EvaluationControl
      gameId={props.gameId}
      selectedSeq={props.selectedSeq}
      onEnqueued={props.onEnqueued}
    />
  );
  if (props.gameId) {
    await waitFor(() =>
      expect(listGameRounds).toHaveBeenCalledWith(props.gameId)
    );
  }
}

describe("EvaluationControl", () => {
  it("disables submission when no game is selected", async () => {
    await renderControl({ gameId: null, selectedSeq: 5 });
    expect(screen.getByTestId("eval-submit")).toBeDisabled();
    // With no game there is nothing to list rounds for.
    expect(listGameRounds).not.toHaveBeenCalled();
  });

  it("requires a selected event when grading the selected move", async () => {
    await renderControl({ gameId: "g1", selectedSeq: null });

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
      targets: [],
    });
    const onEnqueued = vi.fn();
    await renderControl({ gameId: "g1", selectedSeq: 12, onEnqueued });

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
    await renderControl({ gameId: "g1", selectedSeq: null });

    fireEvent.click(screen.getByTestId("eval-move-source-range"));
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

  it("grades a round without any move selected", async () => {
    // The reported defect: picking a round used to require clicking a MOVE inside
    // it so the server could resolve the containing round.
    requestEvaluation.mockResolvedValue({
      request_id: "req-r",
      game_id: "g1",
      scope: "round",
      created_count: 13,
      skipped_count: 0,
      targets: [],
    });
    const user = userEvent.setup();
    await renderControl({ gameId: "g1", selectedSeq: null });

    fireEvent.click(screen.getByTestId("eval-choice-rounds"));
    // The picker offers the service's real rounds, labelled by round of play.
    expect(await screen.findByTestId("eval-round-picker")).toBeInTheDocument();
    expect(screen.getByTestId("eval-round-1")).toHaveTextContent("Round 1");
    expect(screen.getByTestId("eval-round-1")).toHaveTextContent("12 moves");
    expect(screen.getByTestId("eval-round-1")).toHaveTextContent("#1–#30");
    expect(screen.getByTestId("eval-round-2")).toHaveTextContent("Round 2");

    await activate(user, "eval-round-2", "checkbox");
    fireEvent.click(screen.getByTestId("eval-submit"));

    await waitFor(() => {
      // Submitted by round-of-play number, with no seqs and no seq_range, and with no
      // "select an event" complaint despite selectedSeq being null.
      expect(requestEvaluation).toHaveBeenCalledWith("g1", {
        scope: "round",
        selection: { rounds: [2] },
        force: false,
      });
    });
    expect(screen.queryByTestId("eval-error")).not.toBeInTheDocument();
  });

  it("submits several rounds at once", async () => {
    requestEvaluation.mockResolvedValue({
      request_id: "req-r2",
      game_id: "g1",
      scope: "round",
      created_count: 24,
      skipped_count: 0,
      targets: [],
    });
    const user = userEvent.setup();
    await renderControl({ gameId: "g1", selectedSeq: null });

    fireEvent.click(screen.getByTestId("eval-choice-rounds"));
    await screen.findByTestId("eval-round-1");
    await activate(user, "eval-round-1", "checkbox");
    await activate(user, "eval-round-2", "checkbox");
    fireEvent.click(screen.getByTestId("eval-submit"));

    await waitFor(() => {
      expect(requestEvaluation).toHaveBeenCalledWith("g1", {
        scope: "round",
        selection: { rounds: [1, 2] },
        force: false,
      });
    });
  });

  it("asks for a round instead of silently submitting nothing", async () => {
    await renderControl({ gameId: "g1", selectedSeq: 12 });

    fireEvent.click(screen.getByTestId("eval-choice-rounds"));
    fireEvent.click(screen.getByTestId("eval-submit"));

    expect(await screen.findByTestId("eval-error")).toHaveTextContent(
      /pick at least one round/i
    );
    // The selected transcript event must NOT be used as a stand-in for a round.
    expect(requestEvaluation).not.toHaveBeenCalled();
  });

  it("explains a game with no closed round rather than offering an empty list", async () => {
    await renderControl({ gameId: "g1", selectedSeq: null, rounds: [] });

    fireEvent.click(screen.getByTestId("eval-choice-rounds"));
    expect(await screen.findByTestId("eval-rounds-empty")).toHaveTextContent(
      /no round has closed/i
    );
  });

  it("surfaces a failure to load the rounds", async () => {
    await renderControl({
      gameId: "g1",
      selectedSeq: null,
      roundsError: new Error("eval-service unreachable"),
    });

    fireEvent.click(screen.getByTestId("eval-choice-rounds"));
    expect(await screen.findByTestId("eval-rounds-error")).toHaveTextContent(
      /eval-service unreachable/i
    );
  });

  it("submits the whole game with no further target input", async () => {
    requestEvaluation.mockResolvedValue({
      request_id: "req-g",
      game_id: "g1",
      scope: "game",
      created_count: 0,
      skipped_count: 0,
      targets: [],
    });
    await renderControl({ gameId: "g1", selectedSeq: 3 });

    fireEvent.click(screen.getByTestId("eval-choice-game"));
    // Choosing the whole game removes the move and round follow-ups entirely: the
    // transcript selection has no bearing on what is submitted.
    expect(screen.queryByTestId("eval-round-picker")).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("eval-move-source-range")
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("eval-submit"));

    await waitFor(() => {
      expect(requestEvaluation).toHaveBeenCalledWith("g1", {
        scope: "game",
        selection: { whole_game: true },
        force: false,
      });
    });
  });

  it("carries the re-evaluate flag", async () => {
    requestEvaluation.mockResolvedValue({
      request_id: "req-3",
      game_id: "g1",
      scope: "game",
      created_count: 0,
      skipped_count: 0,
      targets: [],
    });
    const user = userEvent.setup();
    await renderControl({ gameId: "g1", selectedSeq: 3 });

    fireEvent.click(screen.getByTestId("eval-choice-game"));
    await activate(user, "eval-force", "switch");
    fireEvent.click(screen.getByTestId("eval-submit"));

    await waitFor(() => {
      expect(requestEvaluation).toHaveBeenCalledWith("g1", {
        scope: "game",
        selection: { whole_game: true },
        force: true,
      });
    });
  });
});
