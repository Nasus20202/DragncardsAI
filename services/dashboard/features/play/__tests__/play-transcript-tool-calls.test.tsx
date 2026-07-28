import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import {
  JobDetail,
  JobEventResponse,
  JsonValue,
  SessionDetail,
} from "@/features/shared/lib/types";

/**
 * Counts how often a tool card's view is built. Building the view is the only
 * work a collapsed tool card does, so this is the DRA-8 regression guard for
 * tool exchanges: a streamed token in one job must not rebuild the cards of
 * every settled tool call in the session.
 */
const viewBuilds = vi.fn();
vi.mock(
  "@/features/play/lib/tool-call-presentation",
  async (importOriginal) => {
    const actual =
      await importOriginal<
        typeof import("@/features/play/lib/tool-call-presentation")
      >();
    return {
      ...actual,
      buildToolExchangeView: (
        ...args: Parameters<typeof actual.buildToolExchangeView>
      ) => {
        viewBuilds();
        return actual.buildToolExchangeView(...args);
      },
    };
  }
);

const { PlayTranscript } =
  await import("@/features/play/components/play-transcript");

const selectedSession: SessionDetail = {
  id: "session-1",
  name: "Session",
  status: "active",
  context_recent_message_limit: null,
  context_recent_tool_exchange_limit: null,
  metadata: {},
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
  terminated_at: null,
  model_config: null,
  skills: [],
  mcps: [],
  recent_job: null,
  recent_jobs: [],
};

let eventSeq = 0;

function event(
  eventType: string,
  payload: Record<string, JsonValue>
): JobEventResponse {
  eventSeq += 1;
  return {
    id: `event-${eventSeq}`,
    event_type: eventType,
    payload,
    created_at: `2026-07-28T00:00:${String(eventSeq).padStart(2, "0")}Z`,
  };
}

function toolCall(
  name: string,
  args: Record<string, JsonValue>,
  callId: string
): JobEventResponse {
  return event("tool_call", {
    tool_call_id: callId,
    exposed_tool_name: name,
    tool_name: name,
    assignment: "game-service",
    server_url: null,
    arguments: args,
  });
}

function toolResult(
  name: string,
  text: string,
  callId: string,
  isError = false
): JobEventResponse {
  return event("tool_result", {
    tool_call_id: callId,
    exposed_tool_name: name,
    tool_name: name,
    assignment: "game-service",
    server_url: null,
    is_error: isError,
    result: { is_error: isError, content: [{ type: "text", text }] },
  });
}

function makeJob(
  id: string,
  events: JobEventResponse[],
  status = "completed"
): JobDetail {
  return {
    id,
    prompt: `Prompt ${id}`,
    metadata: {},
    status,
    attempts: 1,
    max_attempts: 1,
    error_code: null,
    error_message: null,
    result_text: null,
    cancellation_requested_at: null,
    created_at: "2026-07-28T00:00:00Z",
    started_at: null,
    completed_at: null,
    latest_event_id: events.at(-1)?.id ?? null,
    latest_event_type: events.at(-1)?.event_type ?? null,
    outputs: [],
    events,
    available_tools: [],
  };
}

function renderTranscript(
  jobs: JobDetail[],
  options: {
    onViewSubagent?: (childJobId: string, name: string) => void;
    streamingJobId?: string | null;
  } = {}
) {
  return render(
    <PlayTranscript
      jobs={jobs}
      streamingJobId={options.streamingJobId ?? null}
      selectedSession={selectedSession}
      streamState="idle"
      statusText="Ready"
      isBusy={false}
      errorText={null}
      onOpenSettings={vi.fn()}
      onViewSubagent={options.onViewSubagent}
      settingsOpen={false}
    />
  );
}

beforeEach(() => {
  viewBuilds.mockClear();
  Object.defineProperty(globalThis, "ResizeObserver", {
    configurable: true,
    writable: true,
    value: class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  });
  HTMLElement.prototype.scrollTo = vi.fn();
  HTMLElement.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("generic tool exchange", () => {
  it("shows the tool name and its arguments instead of a JSON blob", () => {
    renderTranscript([
      makeJob("job-1", [
        toolCall("move_card", { card_id: "01001a", to: "player1Play" }, "c1"),
        toolResult("move_card", "card moved", "c1"),
      ]),
    ]);

    expect(screen.getByText("move_card")).toBeInTheDocument();
    expect(
      screen.getByText(/card_id: 01001a\s+·\s+to: player1Play/)
    ).toBeInTheDocument();
    // One card for the exchange, not one per event.
    expect(screen.getAllByTestId("tool-exchange")).toHaveLength(1);
    // Nothing is expanded, so the result is not in the document yet.
    expect(screen.queryByText("card moved")).toBeNull();
  });

  it("names each argument and the result once expanded", () => {
    renderTranscript([
      makeJob("job-1", [
        toolCall("move_card", { card_id: "01001a" }, "c1"),
        toolResult("move_card", "card moved", "c1"),
      ]),
    ]);

    fireEvent.click(
      screen.getByRole("button", { name: /expand tool call: move_card/i })
    );

    expect(screen.getByText("Arguments")).toBeInTheDocument();
    expect(screen.getByText("card_id")).toBeInTheDocument();
    expect(screen.getByText("01001a")).toBeInTheDocument();
    expect(screen.getByText("Result")).toBeInTheDocument();
    expect(screen.getByText("card moved")).toBeInTheDocument();
    expect(screen.getByText(/via game-service/)).toBeInTheDocument();
  });

  it("marks a failed call and redacts a credential in the error it surfaces", () => {
    renderTranscript([
      makeJob("job-1", [
        toolCall("draw_card", { count: 1 }, "c1"),
        toolResult(
          "draw_card",
          "gateway rejected the request: api_key=sk-live-abcdefghijkl",
          "c1",
          true
        ),
      ]),
    ]);

    expect(screen.getByTestId("tool-error-chip")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /expand tool call: draw_card/i })
    );
    const body = screen.getByText(/gateway rejected the request/);
    expect(body).toHaveTextContent("[REDACTED]");
    expect(document.body.textContent).not.toContain("sk-live-abcdefghijkl");
  });

  it("never renders an argument whose name says it is a credential", () => {
    renderTranscript([
      makeJob("job-1", [
        toolCall(
          "call_vendor",
          { api_key: "hunter2hunter2hunter2", endpoint: "/cards" },
          "c1"
        ),
        toolResult("call_vendor", "ok", "c1"),
      ]),
    ]);

    expect(document.body.textContent).not.toContain("hunter2");
    fireEvent.click(
      screen.getByRole("button", { name: /expand tool call: call_vendor/i })
    );
    expect(screen.getByText("api_key")).toBeInTheDocument();
    expect(screen.getByText("[REDACTED]")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("hunter2");
    // The redacted row offers no "show all" escape hatch back to the value.
    expect(
      screen.queryByRole("button", { name: /show all of api_key/i })
    ).toBeNull();
  });

  it("shows a call with no result yet as still running", () => {
    renderTranscript([
      makeJob("job-1", [toolCall("get_game_state", {}, "c1")], "running"),
    ]);

    fireEvent.click(
      screen.getByRole("button", { name: /expand tool call: get_game_state/i })
    );
    expect(screen.getByText("Still running…")).toBeInTheDocument();
  });
});

describe("system tool exchanges", () => {
  it("offers a way into the subagent a spawn_subagent call started", () => {
    const onViewSubagent = vi.fn();
    renderTranscript(
      [
        makeJob("job-1", [
          toolCall(
            "spawn_subagent",
            { prompt: "check the villain deck" },
            "c1"
          ),
          toolResult(
            "spawn_subagent",
            JSON.stringify({
              child_job_id: "child-123",
              name: "check the villain deck",
            }),
            "c1"
          ),
        ]),
      ],
      { onViewSubagent }
    );

    expect(
      screen.getByTestId("tool-exchange-subagent-launch")
    ).toBeInTheDocument();
    expect(
      screen.getByText(/started check the villain deck/)
    ).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("tool-view-subagent"));
    expect(onViewSubagent).toHaveBeenCalledWith(
      "child-123",
      "check the villain deck"
    );
  });

  it("omits the view affordance when there is nowhere to open it", () => {
    renderTranscript([
      makeJob("job-1", [
        toolCall("spawn_subagent", { prompt: "check the deck" }, "c1"),
        toolResult(
          "spawn_subagent",
          JSON.stringify({ child_job_id: "child-123", name: "check the deck" }),
          "c1"
        ),
      ]),
    ]);

    expect(screen.queryByTestId("tool-view-subagent")).toBeNull();
  });

  it("names the seat a prompt_player_agent call went to", () => {
    renderTranscript([
      makeJob("job-1", [
        toolCall(
          "prompt_player_agent",
          { player_id: "player2", prompt: "take your turn" },
          "c1"
        ),
        toolResult(
          "prompt_player_agent",
          JSON.stringify({
            child_job_id: "child-9",
            name: "Spider-Man",
            player_id: "player2",
          }),
          "c1"
        ),
      ]),
    ]);

    const card = screen.getByTestId("tool-exchange-subagent-launch");
    expect(card).toHaveTextContent("player2");
    expect(card).toHaveTextContent("started Spider-Man");
  });

  it("shows a loading animation while wait_for_subagent is blocked", () => {
    const { rerender } = renderTranscript([
      makeJob(
        "job-1",
        [toolCall("wait_for_subagent", { child_job_id: "child-123" }, "c1")],
        "running"
      ),
    ]);

    const waiting = screen.getByTestId("tool-wait-spinner");
    expect(waiting).toHaveAttribute("role", "status");
    expect(waiting).toHaveTextContent("waiting for child-12…");
    // A spinner really is animating, not a static label.
    expect(
      screen.getByTestId("tool-exchange-subagent-wait").querySelector("svg")
    ).not.toBeNull();

    // Once the report lands the animation is replaced by the outcome.
    const call = toolCall(
      "wait_for_subagent",
      { child_job_id: "child-123" },
      "c1"
    );
    rerender(
      <PlayTranscript
        jobs={[
          makeJob("job-1", [
            call,
            toolResult("wait_for_subagent", "the deck holds 30 cards", "c1"),
          ]),
        ]}
        streamingJobId={null}
        selectedSession={selectedSession}
        streamState="idle"
        statusText="Ready"
        isBusy={false}
        errorText={null}
        onOpenSettings={vi.fn()}
        settingsOpen={false}
      />
    );

    expect(screen.queryByTestId("tool-wait-spinner")).toBeNull();
    expect(screen.getByTestId("tool-exchange-subagent-wait")).toHaveTextContent(
      "collected child-12…"
    );
  });

  it("puts the skill name on a load_skill card and its content behind the collapse", () => {
    renderTranscript([
      makeJob("job-1", [
        toolCall("load_skill", { skill_name: "marvel-champions" }, "c1"),
        toolResult("load_skill", "# Marvel Champions\nrules go here", "c1"),
      ]),
    ]);

    const card = screen.getByTestId("tool-exchange-skill-load");
    expect(card).toHaveTextContent("marvel-champions");
    expect(card).toHaveTextContent("32 chars");
    expect(screen.queryByText(/rules go here/)).toBeNull();

    fireEvent.click(
      screen.getByRole("button", { name: /expand tool call: load_skill/i })
    );
    expect(screen.getByText("Skill content")).toBeInTheDocument();
    expect(screen.getByText(/rules go here/)).toBeInTheDocument();
  });
});

describe("large payloads", () => {
  const bigCardList = Array.from({ length: 20_000 }, (_, i) => ({
    card_id: `card-${i}`,
    name: `Card number ${i} with a long printed name`,
  }));
  const bigResultText = JSON.stringify(bigCardList);

  it("keeps a huge payload out of the collapsed card", () => {
    renderTranscript([
      makeJob("job-1", [
        toolCall(
          "search_cards_marvel_champions",
          { filters: bigCardList, query: "spider" },
          "c1"
        ),
        toolResult("search_cards_marvel_champions", bigResultText, "c1"),
      ]),
    ]);

    const card = screen.getByTestId("tool-exchange");
    // The summary describes the shape of the big argument; it does not print it.
    expect(card).toHaveTextContent("filters: [20000 items]");
    expect(card.textContent ?? "").not.toContain("card-19999");
    // The whole collapsed card stays a header-sized amount of text.
    expect((card.textContent ?? "").length).toBeLessThan(400);
  });

  it("caps what an expanded card renders and offers the rest on request", () => {
    renderTranscript([
      makeJob("job-1", [
        toolCall(
          "search_cards_marvel_champions",
          { filters: bigCardList },
          "c1"
        ),
        toolResult("search_cards_marvel_champions", bigResultText, "c1"),
      ]),
    ]);

    fireEvent.click(
      screen.getByRole("button", {
        name: /expand tool call: search_cards_marvel_champions/i,
      })
    );

    const card = screen.getByTestId("tool-exchange");
    const expandedLength = (card.textContent ?? "").length;
    expect(expandedLength).toBeLessThan(bigResultText.length / 4);
    expect(
      screen.getByRole("button", { name: /show all of the result/i })
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /show all of filters/i })
    );
    expect((card.textContent ?? "").length).toBeGreaterThan(expandedLength);
  });

  it("does not rebuild settled tool cards when another job streams a token", () => {
    const settled = [
      makeJob("job-1", [
        toolCall("get_game_state", { session_id: "s1" }, "c1"),
        toolResult("get_game_state", bigResultText, "c1"),
      ]),
      makeJob("job-2", [
        toolCall(
          "search_cards_marvel_champions",
          { filters: bigCardList },
          "c2"
        ),
        toolResult("search_cards_marvel_champions", bigResultText, "c2"),
      ]),
    ];
    const streamingEvent = event("model_output", { text: "thinking" });
    const streaming = makeJob("job-3", [streamingEvent], "running");

    let rerender: (ui: React.ReactElement) => void = () => {};
    act(() => {
      rerender = renderTranscript([...settled, streaming], {
        streamingJobId: "job-3",
      }).rerender;
    });
    expect(viewBuilds).toHaveBeenCalledTimes(2);

    // Exactly what `applyStreamEventToJob` produces for one token: a new events
    // array on the streaming job only, with the settled jobs kept by identity.
    viewBuilds.mockClear();
    act(() => {
      rerender(
        <PlayTranscript
          jobs={[
            ...settled,
            makeJob(
              "job-3",
              [event("model_output", { text: "thinking harder" })],
              "running"
            ),
          ]}
          streamingJobId="job-3"
          selectedSession={selectedSession}
          streamState="idle"
          statusText="Ready"
          isBusy={false}
          errorText={null}
          onOpenSettings={vi.fn()}
          settingsOpen={false}
        />
      );
    });

    expect(viewBuilds).not.toHaveBeenCalled();
  });
});
