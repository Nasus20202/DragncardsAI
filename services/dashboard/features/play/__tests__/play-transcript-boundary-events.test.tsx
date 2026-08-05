import "@testing-library/jest-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PlayTranscript } from "@/features/play/components/play-transcript";
import {
  JobDetail,
  JobEventResponse,
  JsonValue,
  SessionDetail,
} from "@/features/shared/lib/types";

/**
 * The two rows an orchestrated game adds to the transcript: a tool call refused
 * for naming another seat's cards, and a finding that a seat broke the rules.
 * Every string in both comes from a model or from the server, so each assertion
 * here is also a check that it is rendered as plain text.
 */

HTMLElement.prototype.scrollIntoView = vi.fn();

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

function makeJob(events: JobEventResponse[]): JobDetail {
  return {
    id: "job-1",
    prompt: "Take your turn",
    metadata: {},
    status: "completed",
    attempts: 1,
    max_attempts: 1,
    error_code: null,
    error_message: null,
    result_text: null,
    cancellation_requested_at: null,
    created_at: "2026-07-28T00:00:00Z",
    started_at: "2026-07-28T00:00:01Z",
    completed_at: "2026-07-28T00:00:02Z",
    latest_event_id: events.at(-1)?.id ?? null,
    latest_event_type: events.at(-1)?.event_type ?? null,
    outputs: [],
    events,
    available_tools: [],
  };
}

function makeEvent(
  eventType: string,
  payload: Record<string, JsonValue>
): JobEventResponse {
  return {
    id: "event-1",
    event_type: eventType,
    payload,
    created_at: "2026-07-28T00:00:01Z",
  };
}

function renderEvents(events: JobEventResponse[]) {
  render(
    <PlayTranscript
      jobs={[makeJob(events)]}
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
}

describe("seat-scope violations in the transcript", () => {
  it("reads as a refusal that names the offending argument and the foreign seat", () => {
    renderEvents([
      makeEvent("seat_scope_violation", {
        player_id: "player1",
        foreign_player_id: "player2",
        tool_name: "game-service_move_card",
        argument: "dest_group_id",
        value: "player2Hand",
        message: "Refused: dest_group_id names player2.",
      }),
    ]);

    const row = screen.getByTestId("seat-scope-violation");
    expect(row).toHaveTextContent("Refused: seat boundary held");
    expect(row).toHaveTextContent("player1 named player2 in dest_group_id");
    expect(row).toHaveTextContent("player2Hand");
    expect(row).toHaveTextContent("game-service_move_card was not called");
  });

  it("is not styled as an error, because the boundary held", () => {
    renderEvents([
      makeEvent("seat_scope_violation", {
        player_id: "player1",
        foreign_player_id: "player3",
        tool_name: "game-service_exhaust_card",
        argument: "player_n",
        value: "player3",
        message: "Refused.",
      }),
    ]);

    expect(screen.getByTestId("seat-scope-violation").className).toContain(
      "warning"
    );
    expect(screen.getByTestId("seat-scope-violation").className).not.toContain(
      "danger"
    );
  });

  it("falls back to the generic block when the payload names no seats", () => {
    renderEvents([
      makeEvent("seat_scope_violation", { message: "something happened" }),
    ]);

    expect(
      screen.queryByTestId("seat-scope-violation")
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Expand Seat boundary refusal" })
    ).toBeInTheDocument();
  });
});

describe("illegal-action findings in the transcript", () => {
  it("shows an unresolved finding as open, naming the seat and the violation", () => {
    renderEvents([
      makeEvent("illegal_action_finding", {
        finding_id: "finding-1",
        player_id: "player2",
        violation: "Played a second ally while at the ally limit",
        required_undo: "Discard the second ally",
        status: "open",
        round_number: 4,
      }),
    ]);

    const row = screen.getByTestId("illegal-action-finding");
    expect(row).toHaveAttribute("data-status", "open");
    expect(row).toHaveTextContent("Open finding");
    expect(row).toHaveTextContent("player2, round 4");
    expect(row).toHaveTextContent(
      "Played a second ally while at the ally limit"
    );
    expect(row).toHaveTextContent("to undo: Discard the second ally");
  });

  it("shows a resolved finding as resolved, with the verification note", () => {
    renderEvents([
      makeEvent("illegal_action_finding", {
        finding_id: "finding-1",
        player_id: "player2",
        violation: "Played a second ally while at the ally limit",
        required_undo: "Discard the second ally",
        status: "resolved",
        round_number: 4,
        resolution_note: "The ally is back in the discard pile",
      }),
    ]);

    const row = screen.getByTestId("illegal-action-finding");
    expect(row).toHaveAttribute("data-status", "resolved");
    expect(row).toHaveTextContent("Resolved finding");
    expect(row).toHaveTextContent("The ally is back in the discard pile");
    expect(row).not.toHaveTextContent("to undo:");
  });

  it("treats an unrecognised status as still open", () => {
    renderEvents([
      makeEvent("illegal_action_finding", {
        player_id: "player1",
        violation: "Advanced the phase",
        status: "probably fine",
      }),
    ]);

    expect(screen.getByTestId("illegal-action-finding")).toHaveAttribute(
      "data-status",
      "open"
    );
  });

  it("falls back to the generic block when the payload names no seat", () => {
    renderEvents([
      makeEvent("illegal_action_finding", { violation: "unattributed" }),
    ]);

    expect(
      screen.queryByTestId("illegal-action-finding")
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Expand Illegal action finding" })
    ).toBeInTheDocument();
  });
});
