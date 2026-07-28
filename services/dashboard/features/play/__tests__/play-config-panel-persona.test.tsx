import "@testing-library/jest-dom";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
};

function renderPanel(overrides: Partial<SessionDraft> = {}) {
  const onDraftChange = vi.fn();
  render(
    <PlayConfigPanel
      canSave
      draft={{ ...draft, ...overrides }}
      isBusy={false}
      isOpen
      mcps={[]}
      modelOptions={["gpt-4o-mini"]}
      providers={[]}
      skills={[]}
      onClose={vi.fn()}
      onDraftChange={onDraftChange}
      onSave={vi.fn()}
      onTerminate={vi.fn()}
      onToggleMcp={vi.fn()}
      onAddMcp={vi.fn()}
      onDeleteMcp={vi.fn()}
    />
  );
  return { onDraftChange };
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.listPersonas.mockResolvedValue([]);
});

describe("PlayConfigPanel subagent persona picker", () => {
  it("is absent when no personas are defined", async () => {
    renderPanel();

    await waitFor(() => expect(apiMocks.listPersonas).toHaveBeenCalled());
    expect(
      screen.queryByTestId("subagent-persona-trigger")
    ).not.toBeInTheDocument();
  });

  it("offers the defined personas and reports the choice on the draft", async () => {
    apiMocks.listPersonas.mockResolvedValue([
      {
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
      },
    ]);

    const { onDraftChange } = renderPanel();

    await userEvent.click(
      await screen.findByTestId("subagent-persona-trigger")
    );
    await userEvent.click(
      await screen.findByRole("option", { name: "rules-lawyer" })
    );

    expect(onDraftChange).toHaveBeenCalledWith(
      expect.objectContaining({ defaultSubagentPersona: "rules-lawyer" })
    );
  });

  it("shows the persona a session is already pinned to", async () => {
    renderPanel({ defaultSubagentPersona: "rules-lawyer" });

    expect(
      await screen.findByTestId("subagent-persona-trigger")
    ).toHaveTextContent("rules-lawyer");
  });
});
