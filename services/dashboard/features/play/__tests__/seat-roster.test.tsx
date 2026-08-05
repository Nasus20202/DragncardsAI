import "@testing-library/jest-dom";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { PlayConfigPanel } from "@/features/play/components/play-config-panel";
import { installResizeObserver } from "@/features/shared/__tests__/heroui-test-env";
import {
  PersonaResponse,
  PlayerConfigResponse,
  SessionDraft,
} from "@/features/shared/lib/types";

const apiMocks = vi.hoisted(() => ({
  listPersonas: vi.fn(),
  setPlayerAgent: vi.fn(),
}));

vi.mock("@/features/play/lib/client-api", () => apiMocks);

beforeAll(installResizeObserver);

const draft: SessionDraft = {
  name: "Session",
  providerId: "openai",
  modelName: "gpt-4o-mini",
  recentMessageLimit: "",
  recentToolExchangeLimit: "",
  reasoning: { enabled: false, effort: "medium", maxTokens: "" },
  gatewayOptionsText: "{}",
  providerOptionsText: "{}",
  selectedSkills: [],
  defaultSubagentPersona: "",
  sessionPersona: "",
  allowedSubagents: [],
  sessionMode: "orchestrated",
};

const persona: PersonaResponse = {
  name: "rules-lawyer",
  display_name: null,
  description: null,
  system_prompt: "Answer from the rules.",
  provider_id: null,
  model_name: null,
  reasoning: null,
  skills: null,
  allowed_tools: null,
  gateway_options: {},
  provider_options: {},
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
};

function makeSeat(
  overrides: Partial<PlayerConfigResponse> = {}
): PlayerConfigResponse {
  return {
    player_id: "player1",
    display_name: null,
    provider_id: null,
    model_name: null,
    reasoning: null,
    skills: null,
    persona: null,
    agent_session_id: null,
    gateway_options: {},
    provider_options: {},
    created_at: "2026-07-28T00:00:00Z",
    updated_at: "2026-07-28T00:00:00Z",
    ...overrides,
  };
}

const seats: PlayerConfigResponse[] = [
  makeSeat({
    player_id: "player1",
    display_name: "Spider-Man",
    persona: "rules-lawyer",
    model_name: "gpt-4o-mini",
    agent_session_id: "seat-session-1",
  }),
  makeSeat({ player_id: "player2", model_name: "gemini-2.0-flash" }),
];

function renderPanel({
  overrides = {},
  players = seats,
  sessionId = "session-1" as string | null,
}: {
  overrides?: Partial<SessionDraft>;
  players?: PlayerConfigResponse[];
  sessionId?: string | null;
} = {}) {
  const onOpenSeatContext = vi.fn();
  render(
    <PlayConfigPanel
      canSave
      draft={{ ...draft, ...overrides }}
      isBusy={false}
      isOpen
      mcps={[]}
      modelOptions={["gemini-2.0-flash", "gpt-4o-mini"]}
      players={players}
      providers={[]}
      sessionId={sessionId}
      skills={[]}
      onClose={vi.fn()}
      onDraftChange={vi.fn()}
      onOpenSeatContext={onOpenSeatContext}
      onSave={vi.fn()}
      onTerminate={vi.fn()}
      onToggleMcp={vi.fn()}
      onAddMcp={vi.fn()}
      onDeleteMcp={vi.fn()}
    />
  );
  return { onOpenSeatContext };
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.listPersonas.mockResolvedValue([persona]);
  apiMocks.setPlayerAgent.mockImplementation(
    async (_sessionId: string, playerId: string) =>
      makeSeat({ player_id: playerId })
  );
});

describe("SeatRoster", () => {
  it("lists each configured seat with its identifier, persona, and model", async () => {
    renderPanel();

    await waitFor(() => expect(apiMocks.listPersonas).toHaveBeenCalled());

    expect(screen.getByTestId("seat-row-player1")).toHaveTextContent("player1");
    expect(screen.getByTestId("seat-row-player1")).toHaveTextContent(
      "Spider-Man"
    );
    expect(
      screen.getByTestId("seat-persona-trigger-player1")
    ).toHaveTextContent("rules-lawyer");
    expect(screen.getByTestId("seat-model-trigger-player1")).toHaveTextContent(
      "gpt-4o-mini"
    );

    expect(screen.getByTestId("seat-row-player2")).toHaveTextContent("player2");
    expect(screen.getByTestId("seat-model-trigger-player2")).toHaveTextContent(
      "gemini-2.0-flash"
    );
  });

  it("names the inherited model on a seat that overrides none", async () => {
    renderPanel({ players: [makeSeat({ player_id: "player1" })] });

    await waitFor(() => expect(apiMocks.listPersonas).toHaveBeenCalled());

    expect(screen.getByTestId("seat-model-trigger-player1")).toHaveTextContent(
      "Inherited (gpt-4o-mini)"
    );
  });

  it("is absent for a session in chat mode", async () => {
    renderPanel({ overrides: { sessionMode: "chat" } });

    await waitFor(() => expect(apiMocks.listPersonas).toHaveBeenCalled());
    expect(screen.queryByTestId("seat-roster")).not.toBeInTheDocument();
    expect(screen.queryByTestId("seat-row-player1")).not.toBeInTheDocument();
  });

  it("sends a seat's new persona, carrying the rest of the seat unchanged", async () => {
    renderPanel();

    await userEvent.click(
      await screen.findByTestId("seat-persona-trigger-player2")
    );
    await userEvent.click(
      await screen.findByRole("option", { name: "rules-lawyer" })
    );

    await waitFor(() =>
      expect(apiMocks.setPlayerAgent).toHaveBeenCalledWith(
        "session-1",
        "player2",
        expect.objectContaining({
          persona: "rules-lawyer",
          model_name: "gemini-2.0-flash",
        })
      )
    );
  });

  it("sends a seat's new model", async () => {
    renderPanel();

    await userEvent.click(
      await screen.findByTestId("seat-model-trigger-player1")
    );
    await userEvent.click(
      await screen.findByRole("option", { name: "gemini-2.0-flash" })
    );

    await waitFor(() =>
      expect(apiMocks.setPlayerAgent).toHaveBeenCalledWith(
        "session-1",
        "player1",
        expect.objectContaining({
          model_name: "gemini-2.0-flash",
          persona: "rules-lawyer",
        })
      )
    );
  });

  it("reports a refused seat edit instead of showing it as applied", async () => {
    apiMocks.setPlayerAgent.mockRejectedValue(
      new Error("Unknown persona: rules-lawyer")
    );
    renderPanel();

    await userEvent.click(
      await screen.findByTestId("seat-persona-trigger-player2")
    );
    await userEvent.click(
      await screen.findByRole("option", { name: "rules-lawyer" })
    );

    expect(
      await screen.findByText("Unknown persona: rules-lawyer")
    ).toBeInTheDocument();
  });

  it("offers a prompted seat's own context and says an unprompted seat has none", async () => {
    const { onOpenSeatContext } = renderPanel();

    const openContext = await screen.findByTestId("seat-context-player1");
    expect(
      screen.queryByTestId("seat-context-player2")
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("seat-no-context-player2")).toHaveTextContent(
      "No context yet"
    );

    await userEvent.click(openContext);
    expect(onOpenSeatContext).toHaveBeenCalledWith("seat-session-1");
  });

  it("adds the next free seat, because the orchestrator will not prompt an unconfigured one", async () => {
    renderPanel({ players: [seats[0]] });

    await userEvent.click(await screen.findByTestId("seat-roster-add"));

    await waitFor(() =>
      expect(apiMocks.setPlayerAgent).toHaveBeenCalledWith(
        "session-1",
        "player2",
        expect.objectContaining({ reasoning: { enabled: false } })
      )
    );
    expect(await screen.findByTestId("seat-row-player2")).toBeInTheDocument();
  });

  it("says seats are configured after the session exists", async () => {
    renderPanel({ players: [], sessionId: null });

    expect(
      await screen.findByText("Create the session to configure its seats.")
    ).toBeInTheDocument();
    expect(screen.queryByTestId("seat-roster-add")).not.toBeInTheDocument();
  });
});
