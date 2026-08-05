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
  sessionPersona: "",
  allowedSubagents: [],
  sessionMode: "chat",
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

function persona(name: string, description: string | null = null) {
  return {
    name,
    display_name: null,
    description,
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
}

describe("PlayConfigPanel subagent persona picker", () => {
  it("is absent when no personas are defined", async () => {
    renderPanel();

    await waitFor(() => expect(apiMocks.listPersonas).toHaveBeenCalled());
    expect(
      screen.queryByTestId("subagent-persona-trigger")
    ).not.toBeInTheDocument();
  });

  it("offers only the personas this session is allowed to spawn", async () => {
    apiMocks.listPersonas.mockResolvedValue([
      persona("rules-lawyer"),
      persona("scout"),
    ]);

    const { onDraftChange } = renderPanel({
      allowedSubagents: ["rules-lawyer"],
    });

    await userEvent.click(
      await screen.findByTestId("subagent-persona-trigger")
    );
    // `scout` exists in the catalogue but this session may not spawn it, so
    // offering it would produce a default whose one effect is a refusal.
    expect(
      screen.queryByRole("option", { name: "scout" })
    ).not.toBeInTheDocument();
    await userEvent.click(
      await screen.findByRole("option", { name: "rules-lawyer" })
    );

    expect(onDraftChange).toHaveBeenCalledWith(
      expect.objectContaining({ defaultSubagentPersona: "rules-lawyer" })
    );
  });

  it("offers nothing while the session allows no subagent persona", async () => {
    apiMocks.listPersonas.mockResolvedValue([persona("rules-lawyer")]);

    renderPanel();

    await waitFor(() => expect(apiMocks.listPersonas).toHaveBeenCalled());
    expect(
      screen.queryByTestId("subagent-persona-trigger")
    ).not.toBeInTheDocument();
  });

  it("shows the persona a session is already pinned to", async () => {
    renderPanel({ defaultSubagentPersona: "rules-lawyer" });

    expect(
      await screen.findByTestId("subagent-persona-trigger")
    ).toHaveTextContent("rules-lawyer");
  });
});

describe("PlayConfigPanel session persona picker", () => {
  it("offers the catalogue and reports the choice on the draft", async () => {
    apiMocks.listPersonas.mockResolvedValue([persona("table-talk")]);

    const { onDraftChange } = renderPanel();

    await userEvent.click(await screen.findByTestId("session-persona-trigger"));
    await userEvent.click(
      await screen.findByRole("option", { name: "table-talk" })
    );

    expect(onDraftChange).toHaveBeenCalledWith(
      expect.objectContaining({ sessionPersona: "table-talk" })
    );
  });

  it("is not narrowed by the subagent allowlist", async () => {
    // The allowlist governs what the agent may DELEGATE to. What the session's
    // own agent runs as is the operator's separate choice, so restricting one by
    // the other would conflate two unrelated controls.
    apiMocks.listPersonas.mockResolvedValue([persona("table-talk")]);

    renderPanel({ allowedSubagents: [] });

    expect(
      await screen.findByTestId("session-persona-trigger")
    ).toBeInTheDocument();
  });
});

describe("PlayConfigPanel subagent allowlist", () => {
  it("says in words that nothing ticked means nothing allowed", async () => {
    apiMocks.listPersonas.mockResolvedValue([persona("rules-lawyer")]);

    renderPanel();

    expect(
      await screen.findByTestId("subagent-allowlist-summary")
    ).toHaveTextContent(/No personas allowed/i);
  });

  it("states how many are allowed once some are", async () => {
    apiMocks.listPersonas.mockResolvedValue([
      persona("rules-lawyer"),
      persona("scout"),
    ]);

    renderPanel({ allowedSubagents: ["scout"] });

    expect(
      await screen.findByTestId("subagent-allowlist-summary")
    ).toHaveTextContent(/1 of 2 personas allowed/i);
  });

  it("adds a persona to the allowlist on the draft", async () => {
    apiMocks.listPersonas.mockResolvedValue([
      persona("scout", "Reads boards."),
    ]);

    const { onDraftChange } = renderPanel();

    await userEvent.click(await screen.findByRole("switch", { name: "scout" }));

    expect(onDraftChange).toHaveBeenCalledWith(
      expect.objectContaining({ allowedSubagents: ["scout"] })
    );
  });

  it("clears the default when the persona it names is revoked", async () => {
    // The orchestrator refuses a default outside the allowlist, and rightly: a
    // default nothing may spawn turns every plain spawn into a refusal.
    apiMocks.listPersonas.mockResolvedValue([persona("scout")]);

    const { onDraftChange } = renderPanel({
      allowedSubagents: ["scout"],
      defaultSubagentPersona: "scout",
    });

    await userEvent.click(await screen.findByRole("switch", { name: "scout" }));

    expect(onDraftChange).toHaveBeenCalledWith(
      expect.objectContaining({
        allowedSubagents: [],
        defaultSubagentPersona: "",
      })
    );
  });
});
