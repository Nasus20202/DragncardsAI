import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom";

import {
  BoardActions,
  ExpandSignal,
  HistoryTranscript,
} from "@/features/history/components/history-transcript";
import { scoreColors } from "@/features/history/lib/score-colors";
import { HistoryEvent } from "@/features/shared/lib/types";

// jsdom does not implement scrollIntoView; the scroll-lock auto-follow uses it.
HTMLElement.prototype.scrollIntoView = vi.fn();

/** The background colour of the score chip inside (or at) `element`. */
function background(element: HTMLElement): string | undefined {
  const chip = element.matches("[data-slot='chip']")
    ? element
    : element.querySelector("[data-slot='chip']");
  return (chip as HTMLElement | null)?.style.backgroundColor;
}

const board: BoardActions = {
  gameId: "g1",
  isOpening: false,
  error: null,
  isOpen: false,
  onOpen: vi.fn(),
};

function renderTranscript(
  events: HistoryEvent[],
  selectedSeq: number | null = null,
  onSelect = vi.fn(),
  opts: { expandSignal?: ExpandSignal; searchQuery?: string } = {}
) {
  return render(
    <HistoryTranscript
      events={events}
      selectedSeq={selectedSeq}
      onSelect={onSelect}
      onRestore={vi.fn().mockResolvedValue({})}
      board={board}
      expandSignal={opts.expandSignal}
      searchQuery={opts.searchQuery}
    />
  );
}

const USER_EVENT: HistoryEvent = {
  seq: 0,
  event_id: "u1",
  game_id: "g1",
  actor: "user",
  event_type: "user_prompt",
  payload: { prompt: "Play Ms. Marvel and attack the villain" },
  occurred_at: "2026-06-24T09:59:00Z",
  recorded_at: "2026-06-24T09:59:01Z",
};

const AGENT_EVENT: HistoryEvent = {
  seq: 1,
  event_id: "e1",
  game_id: "g1",
  actor: "agent",
  event_type: "move",
  payload: {
    intended_action: "load_prebuilt_deck",
    reasoning: "Set up the deck",
    conversation_context: [{ role: "assistant", content: "Loading deck" }],
  },
  occurred_at: "2026-06-24T10:00:00Z",
  recorded_at: "2026-06-24T10:00:01Z",
};

const GAME_EVENT: HistoryEvent = {
  seq: 2,
  event_id: "e2",
  game_id: "g1",
  actor: "game-service",
  event_type: "state_changed",
  payload: {
    status: "in progress",
    action_args: { type: "move_card" },
    state: { game: { roundNumber: 0, stepId: "1.1" } },
  },
  occurred_at: "2026-06-24T10:01:00Z",
  recorded_at: "2026-06-24T10:01:01Z",
};

describe("HistoryTranscript", () => {
  it("renders an empty state with no events", () => {
    renderTranscript([]);
    expect(screen.getByTestId("history-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("history-transcript")).not.toBeInTheDocument();
  });

  it("renders every event kind inline as a readable block", () => {
    renderTranscript([USER_EVENT, AGENT_EVENT, GAME_EVENT]);

    // User prompt → right-aligned prompt bubble with the full prompt (always
    // visible; the short user bubble is never collapsed).
    const userBlock = within(screen.getByTestId("history-event-0")).getByTestId(
      "history-detail-user"
    );
    expect(userBlock).toHaveTextContent(
      "Play Ms. Marvel and attack the villain"
    );

    // Agent move → body is collapsed by default; expanding its summary toggle
    // reveals the intended action + reasoning + a collapsed conversation.
    expect(
      within(screen.getByTestId("history-event-1")).queryByTestId(
        "history-detail-agent"
      )
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("history-event-body-toggle-1"));
    const agentBlock = within(
      screen.getByTestId("history-event-1")
    ).getByTestId("history-detail-agent");
    expect(agentBlock).toHaveTextContent("load_prebuilt_deck");
    // The conversation is collapsed by default (unreadable when always open) —
    // its transcript is not rendered until the per-event toggle is expanded.
    expect(
      within(agentBlock).queryByTestId("conversation-transcript")
    ).not.toBeInTheDocument();
    fireEvent.click(
      within(agentBlock).getByTestId("history-conversation-toggle-1")
    );
    expect(
      within(agentBlock).getByTestId("conversation-transcript")
    ).toBeInTheDocument();
    // The action label is humanized.
    expect(screen.getByTestId("history-event-1")).toHaveTextContent(
      "Load prebuilt deck"
    );

    // Game state → expanding the body reveals the status summary; the phase
    // chip stays on the always-visible summary line.
    fireEvent.click(screen.getByTestId("history-event-body-toggle-2"));
    const gameBlock = within(screen.getByTestId("history-event-2")).getByTestId(
      "history-detail-game"
    );
    expect(gameBlock).toHaveTextContent("in progress");
    expect(screen.getByTestId("history-event-phase-2")).toHaveTextContent(
      "Player 1.1"
    );
  });

  it("groups events under sticky round headers", () => {
    renderTranscript([AGENT_EVENT, GAME_EVENT]);
    // Leading event with no game-state inherits "Setup"; the game-state opens
    // "Round 1".
    expect(screen.getByTestId("history-round-setup")).toHaveTextContent(
      "Setup"
    );
    expect(screen.getByTestId("history-round-round-1")).toHaveTextContent(
      "Round 1"
    );
  });

  it("carries data-actor / data-testid and reports selection", () => {
    const onSelect = vi.fn();
    renderTranscript([AGENT_EVENT, GAME_EVENT], null, onSelect);

    const agent = screen.getByTestId("history-event-1");
    expect(agent).toHaveAttribute("data-actor", "agent");
    fireEvent.click(agent);
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it("nests verdicts under the graded event and expands on toggle", () => {
    const verdict: HistoryEvent = {
      seq: 3,
      event_id: "v3",
      game_id: "g1",
      actor: "evaluator",
      event_type: "move_evaluation",
      payload: {
        scope: "move",
        target_seq: 1,
        overall_score: 8,
        rationale: "Solid",
        evaluator: { model: "anthropic/claude" },
      },
      occurred_at: "2026-06-24T10:02:00Z",
      recorded_at: "2026-06-24T10:02:01Z",
    };
    renderTranscript([AGENT_EVENT, verdict]);

    // The verdict is not a standalone row.
    expect(screen.queryByTestId("history-event-3")).not.toBeInTheDocument();
    // The graded move shows a score indicator + collapsed toggle.
    expect(
      screen.getByTestId("history-event-eval-indicator-1")
    ).toHaveTextContent("8/10");
    expect(screen.getByTestId("history-evals-toggle-1")).toHaveTextContent(
      "1 evaluation"
    );
    expect(
      screen.queryByTestId("history-eval-score-3")
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("history-evals-toggle-1"));
    expect(screen.getByTestId("history-eval-score-3")).toHaveTextContent(
      "8/10"
    );
  });

  it("opens the evaluation sub-tree when the move's score chip is clicked", () => {
    const verdict: HistoryEvent = {
      seq: 3,
      event_id: "v3",
      game_id: "g1",
      actor: "evaluator",
      event_type: "move_evaluation",
      payload: { scope: "move", target_seq: 1, overall_score: 8 },
      occurred_at: "2026-06-24T10:02:00Z",
      recorded_at: "2026-06-24T10:02:01Z",
    };
    renderTranscript([AGENT_EVENT, verdict]);

    // Collapsed by default.
    expect(
      screen.queryByTestId("history-eval-score-3")
    ).not.toBeInTheDocument();
    // Clicking the summary score chip reveals the verdict sub-tree.
    fireEvent.click(screen.getByTestId("history-event-eval-indicator-1"));
    expect(screen.getByTestId("history-eval-score-3")).toHaveTextContent(
      "8/10"
    );
  });

  it("opens an event's body when a reveal pulse targets it", () => {
    const { rerender } = render(
      <HistoryTranscript
        events={[AGENT_EVENT, GAME_EVENT]}
        selectedSeq={null}
        onSelect={vi.fn()}
        onRestore={vi.fn().mockResolvedValue({})}
        board={board}
        reveal={{ seq: null, mode: "body", nonce: 0 }}
      />
    );
    // Body collapsed by default.
    expect(
      within(screen.getByTestId("history-event-1")).queryByTestId(
        "history-detail-agent"
      )
    ).not.toBeInTheDocument();
    // A reveal pulse for seq 1 opens its body (as a nav-tree click would).
    rerender(
      <HistoryTranscript
        events={[AGENT_EVENT, GAME_EVENT]}
        selectedSeq={1}
        onSelect={vi.fn()}
        onRestore={vi.fn().mockResolvedValue({})}
        board={board}
        reveal={{ seq: 1, mode: "body", nonce: 1 }}
      />
    );
    expect(
      within(screen.getByTestId("history-event-1")).getByTestId(
        "history-detail-agent"
      )
    ).toBeInTheDocument();
  });

  it("labels a round-scope verdict distinctly from a move-scope one", () => {
    const moveVerdict: HistoryEvent = {
      seq: 3,
      event_id: "v3",
      game_id: "g1",
      actor: "evaluator",
      event_type: "evaluation",
      payload: { scope: "move", target_seq: 1, overall_score: 8 },
      occurred_at: "2026-06-24T10:02:00Z",
      recorded_at: "2026-06-24T10:02:01Z",
    };
    const roundVerdict: HistoryEvent = {
      seq: 4,
      event_id: "v4",
      game_id: "g1",
      actor: "evaluator",
      event_type: "evaluation",
      payload: {
        scope: "round",
        target_seq: 2,
        // The SEQ span the round covered, and separately the round of play it is.
        // The label comes from the latter (DRA-25), so the two deliberately differ.
        round_span: [1, 2],
        round_number: 1,
        overall_score: 6,
      },
      occurred_at: "2026-06-24T10:03:00Z",
      recorded_at: "2026-06-24T10:03:01Z",
    };
    renderTranscript([AGENT_EVENT, GAME_EVENT, moveVerdict, roundVerdict]);

    fireEvent.click(screen.getByTestId("history-evals-toggle-1"));
    fireEvent.click(screen.getByTestId("history-evals-toggle-2"));

    expect(screen.getByTestId("history-eval-scope-3")).toHaveTextContent(
      "Move"
    );
    expect(screen.getByTestId("history-eval-scope-4")).toHaveTextContent(
      "Round 1"
    );
  });

  it("shows the player on each verdict and distinguishes roll-ups from moves", () => {
    const moveVerdict: HistoryEvent = {
      seq: 3,
      event_id: "v3",
      game_id: "g1",
      actor: "evaluator",
      event_type: "evaluation",
      payload: {
        scope: "move",
        target_seq: 1,
        player: "player1",
        overall_score: 8,
      },
      occurred_at: "2026-06-24T10:02:00Z",
      recorded_at: "2026-06-24T10:02:01Z",
    };
    const roundRollup: HistoryEvent = {
      seq: 4,
      event_id: "v4",
      game_id: "g1",
      actor: "evaluator",
      event_type: "evaluation",
      payload: {
        scope: "round",
        target_seq: 1,
        round_span: [1, 1],
        player: "player2",
        overall_score: 6,
      },
      occurred_at: "2026-06-24T10:03:00Z",
      recorded_at: "2026-06-24T10:03:01Z",
    };
    const gameRollup: HistoryEvent = {
      seq: 5,
      event_id: "v5",
      game_id: "g1",
      actor: "evaluator",
      event_type: "evaluation",
      payload: {
        scope: "game",
        target_seq: 1,
        round_span: [1, 1],
        player: "player1",
        overall_score: 7,
      },
      occurred_at: "2026-06-24T10:04:00Z",
      recorded_at: "2026-06-24T10:04:01Z",
    };
    renderTranscript([AGENT_EVENT, moveVerdict, roundRollup, gameRollup]);

    fireEvent.click(screen.getByTestId("history-evals-toggle-1"));

    // Each verdict shows its player as a chip.
    expect(screen.getByTestId("history-eval-player-3")).toHaveTextContent(
      "player1"
    );
    expect(screen.getByTestId("history-eval-player-4")).toHaveTextContent(
      "player2"
    );
    expect(screen.getByTestId("history-eval-player-5")).toHaveTextContent(
      "player1"
    );
    // Round/game roll-ups are marked at a distinct level from the move verdict.
    const list = screen.getByTestId("history-evals-1");
    const rows = within(list).getAllByRole("button");
    expect(rows[0]).toHaveAttribute("data-level", "move");
    expect(rows[1]).toHaveAttribute("data-level", "round");
    expect(rows[2]).toHaveAttribute("data-level", "game");
  });

  it("reveals restore + board actions per event via the Actions toggle", () => {
    renderTranscript([AGENT_EVENT, GAME_EVENT], 1);

    // Actions are an opt-in per-event option, not shown inline by default.
    expect(
      screen.queryByTestId("history-event-actions-1")
    ).not.toBeInTheDocument();

    // Expanding the event's Actions toggle reveals its restore + board controls.
    fireEvent.click(screen.getByTestId("history-event-actions-toggle-1"));
    const actions = screen.getByTestId("history-event-actions-1");
    expect(within(actions).getByTestId("restore-control")).toBeInTheDocument();
    expect(within(actions).getByTestId("board-control")).toBeInTheDocument();
    // The board control acts on this event's seq.
    expect(within(actions).getByTestId("board-open")).toBeEnabled();
    // Another event's actions stay hidden until its own toggle is used.
    expect(
      screen.queryByTestId("history-event-actions-2")
    ).not.toBeInTheDocument();
  });

  it("collapses event bodies by default and toggles a single one open", () => {
    renderTranscript([AGENT_EVENT, GAME_EVENT]);

    // Bodies are collapsed by default — only the summary line shows.
    expect(
      screen.queryByTestId("history-detail-agent")
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("history-detail-game")).not.toBeInTheDocument();

    // A per-event toggle opens just that body.
    fireEvent.click(screen.getByTestId("history-event-body-toggle-1"));
    expect(screen.getByTestId("history-detail-agent")).toBeInTheDocument();
    expect(screen.queryByTestId("history-detail-game")).not.toBeInTheDocument();
  });

  it("syncs all bodies to the global expand/collapse signal", () => {
    const { rerender } = renderTranscript(
      [AGENT_EVENT, GAME_EVENT],
      null,
      vi.fn(),
      {
        expandSignal: { generation: 0, expanded: false },
      }
    );
    expect(
      screen.queryByTestId("history-detail-agent")
    ).not.toBeInTheDocument();

    // Expand all → every body opens.
    rerender(
      <HistoryTranscript
        events={[AGENT_EVENT, GAME_EVENT]}
        selectedSeq={null}
        onSelect={vi.fn()}
        onRestore={vi.fn().mockResolvedValue({})}
        board={board}
        expandSignal={{ generation: 1, expanded: true }}
      />
    );
    expect(screen.getByTestId("history-detail-agent")).toBeInTheDocument();
    expect(screen.getByTestId("history-detail-game")).toBeInTheDocument();

    // Collapse all → every body closes.
    rerender(
      <HistoryTranscript
        events={[AGENT_EVENT, GAME_EVENT]}
        selectedSeq={null}
        onSelect={vi.fn()}
        onRestore={vi.fn().mockResolvedValue({})}
        board={board}
        expandSignal={{ generation: 2, expanded: false }}
      />
    );
    expect(
      screen.queryByTestId("history-detail-agent")
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("history-detail-game")).not.toBeInTheDocument();
  });

  it("filters events by a case-insensitive search query", () => {
    renderTranscript([USER_EVENT, AGENT_EVENT, GAME_EVENT], null, vi.fn(), {
      searchQuery: "prebuilt",
    });
    // Only the agent event (intended_action "load_prebuilt_deck") matches.
    expect(screen.getByTestId("history-event-1")).toBeInTheDocument();
    expect(screen.queryByTestId("history-event-0")).not.toBeInTheDocument();
    expect(screen.queryByTestId("history-event-2")).not.toBeInTheDocument();
  });

  it("shows a no-matches empty state and restores on clear", () => {
    const { rerender } = renderTranscript(
      [USER_EVENT, AGENT_EVENT, GAME_EVENT],
      null,
      vi.fn(),
      { searchQuery: "zzz-nothing" }
    );
    expect(screen.getByTestId("history-search-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("history-event-1")).not.toBeInTheDocument();

    // Clearing the query restores all events.
    rerender(
      <HistoryTranscript
        events={[USER_EVENT, AGENT_EVENT, GAME_EVENT]}
        selectedSeq={null}
        onSelect={vi.fn()}
        onRestore={vi.fn().mockResolvedValue({})}
        board={board}
        searchQuery=""
      />
    );
    expect(
      screen.queryByTestId("history-search-empty")
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("history-event-0")).toBeInTheDocument();
    expect(screen.getByTestId("history-event-1")).toBeInTheDocument();
    expect(screen.getByTestId("history-event-2")).toBeInTheDocument();
  });

  it("renders start and end markers for each round", () => {
    // `roundNumber` counts COMPLETED rounds, so round 1 of play reports 0. The
    // event that reports the next round is the move that CLOSED the previous
    // one, so it ends its round rather than opening the new one.
    const round1State: HistoryEvent = {
      ...GAME_EVENT,
      seq: 10,
      event_id: "g10",
      payload: {
        status: "in progress",
        state: { game: { roundNumber: 0, stepId: "1.1" } },
      },
    };
    const round1Agent: HistoryEvent = {
      ...AGENT_EVENT,
      seq: 11,
      event_id: "a11",
    };
    const round1Close: HistoryEvent = {
      ...GAME_EVENT,
      seq: 12,
      event_id: "g12",
      payload: {
        status: "in progress",
        state: { game: { roundNumber: 1, stepId: "0.0" } },
      },
    };
    const round2Agent: HistoryEvent = {
      ...AGENT_EVENT,
      seq: 13,
      event_id: "a13",
    };
    const round2Close: HistoryEvent = {
      ...GAME_EVENT,
      seq: 14,
      event_id: "g14",
      payload: {
        status: "in progress",
        state: { game: { roundNumber: 2, stepId: "0.0" } },
      },
    };
    const round3Agent: HistoryEvent = {
      ...AGENT_EVENT,
      seq: 15,
      event_id: "a15",
    };
    renderTranscript([
      round1State,
      round1Agent,
      round1Close,
      round2Agent,
      round2Close,
      round3Agent,
    ]);

    expect(screen.getByTestId("history-round-round-1")).toHaveTextContent(
      "Round 1 — start"
    );
    expect(screen.getByTestId("history-round-end-round-1")).toHaveTextContent(
      "Round 1 — end"
    );
    expect(screen.getByTestId("history-round-round-2")).toHaveTextContent(
      "Round 2 — start"
    );
    expect(screen.getByTestId("history-round-end-round-2")).toHaveTextContent(
      "Round 2 — end"
    );
    expect(screen.getByTestId("history-round-round-3")).toHaveTextContent(
      "Round 3 — start"
    );
  });

  it("does not mark the last round in view as ended", () => {
    const round1State: HistoryEvent = {
      ...GAME_EVENT,
      seq: 20,
      event_id: "g20",
      payload: {
        status: "in progress",
        state: { game: { roundNumber: 0, stepId: "1.1" } },
      },
    };
    const round1Agent: HistoryEvent = {
      ...AGENT_EVENT,
      seq: 21,
      event_id: "a21",
    };
    renderTranscript([round1State, round1Agent]);

    // The round is still in progress (or the timeline was cut short): nothing
    // proves it ended, so no end marker may be fabricated.
    expect(screen.getByTestId("history-round-round-1")).toBeInTheDocument();
    expect(
      screen.queryByTestId("history-round-end-round-1")
    ).not.toBeInTheDocument();
  });

  it("colours a score chip from the score rather than always green", () => {
    const verdict = (seq: number, targetSeq: number, score: number) =>
      ({
        seq,
        event_id: `v${seq}`,
        game_id: "g1",
        actor: "evaluator",
        event_type: "move_evaluation",
        payload: { scope: "move", target_seq: targetSeq, overall_score: score },
        occurred_at: "2026-06-24T10:02:00Z",
        recorded_at: "2026-06-24T10:02:01Z",
      }) satisfies HistoryEvent;
    const secondMove: HistoryEvent = {
      ...AGENT_EVENT,
      seq: 2,
      event_id: "a2",
    };
    renderTranscript([
      AGENT_EVENT,
      secondMove,
      verdict(3, 1, 2),
      verdict(4, 2, 9),
    ]);

    // Each move's indicator carries the ramp colour of the score it summarises.
    const low = background(
      screen.getByTestId("history-event-eval-indicator-1")
    );
    const high = background(
      screen.getByTestId("history-event-eval-indicator-2")
    );
    expect(low).toBe(scoreColors(2)?.background);
    expect(high).toBe(scoreColors(9)?.background);
    expect(low).not.toBe(high);

    // The verdict chip in the sub-tree uses the same mapping, so one score is
    // never shown in two colours.
    fireEvent.click(screen.getByTestId("history-evals-toggle-1"));
    expect(background(screen.getByTestId("history-eval-score-3"))).toBe(low);
  });

  it("pairs the score's text colour with its background", () => {
    const verdict: HistoryEvent = {
      seq: 3,
      event_id: "v3",
      game_id: "g1",
      actor: "evaluator",
      event_type: "move_evaluation",
      payload: { scope: "move", target_seq: 1, overall_score: 5 },
      occurred_at: "2026-06-24T10:02:00Z",
      recorded_at: "2026-06-24T10:02:01Z",
    };
    renderTranscript([AGENT_EVENT, verdict]);

    const chip = screen
      .getByTestId("history-event-eval-indicator-1")
      .querySelector("[data-slot='chip']") as HTMLElement;
    expect(chip.style.backgroundColor).toBe(scoreColors(5)?.background);
    expect(chip.style.color).toBe(scoreColors(5)?.foreground);
  });

  it("leaves a verdict with no overall score uncoloured", () => {
    const verdict: HistoryEvent = {
      seq: 3,
      event_id: "v3",
      game_id: "g1",
      actor: "evaluator",
      event_type: "move_evaluation",
      payload: { scope: "move", target_seq: 1, rationale: "No number" },
      occurred_at: "2026-06-24T10:02:00Z",
      recorded_at: "2026-06-24T10:02:01Z",
    };
    renderTranscript([AGENT_EVENT, verdict]);

    // No score means no chip at all — never a chip in the colour of a top score.
    expect(
      screen.queryByTestId("history-event-eval-indicator-1")
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("history-evals-toggle-1"));
    expect(
      screen.queryByTestId("history-eval-score-3")
    ).not.toBeInTheDocument();
  });
});
