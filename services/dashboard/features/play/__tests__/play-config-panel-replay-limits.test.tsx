import "@testing-library/jest-dom";
import { render, screen } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { PlayConfigPanel } from "@/features/play/components/play-config-panel";
import { installResizeObserver } from "@/features/shared/__tests__/heroui-test-env";
import { SessionDraft } from "@/features/shared/lib/types";

const apiMocks = vi.hoisted(() => ({
  listPersonas: vi.fn(),
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
  sessionMode: "chat",
};

function renderPanel() {
  render(
    <PlayConfigPanel
      canSave
      draft={draft}
      isBusy={false}
      isModeLocked={false}
      isOpen
      mcps={[]}
      modelOptions={["gpt-4o-mini"]}
      providers={[]}
      skills={[]}
      onClose={vi.fn()}
      onDraftChange={vi.fn()}
      onSave={vi.fn()}
      onTerminate={vi.fn()}
      onToggleMcp={vi.fn()}
      onAddMcp={vi.fn()}
      onDeleteMcp={vi.fn()}
    />
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.listPersonas.mockResolvedValue([]);
});

/**
 * Both limits take history away from the agent, and which history depends on
 * what the orchestrator keeps: the newest conversational messages, and the
 * newest tool exchanges with a reserved slot for the newest game state. The
 * wording is asserted here so it cannot drift away from
 * `_select_recent_message_orders` / `_select_recent_tool_exchange_orders`.
 */
describe("PlayConfigPanel replay limit fields", () => {
  it("says what the message limit drops", () => {
    renderPanel();

    expect(
      screen.getByText(/newest N conversational messages/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/compaction summary is never dropped/i)
    ).toBeInTheDocument();
  });

  it("says what the tool exchange limit drops", () => {
    renderPanel();

    expect(
      screen.getByText(/newest N tool call\/result pairs/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/newest game-state result always keeps a slot/i)
    ).toBeInTheDocument();
  });
});
