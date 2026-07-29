import "@testing-library/jest-dom";
import { render, screen } from "@testing-library/react";
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
  sessionMode: "chat",
};

function renderPanel({
  overrides = {},
  isModeLocked = false,
}: {
  overrides?: Partial<SessionDraft>;
  isModeLocked?: boolean;
} = {}) {
  const onDraftChange = vi.fn();
  render(
    <PlayConfigPanel
      canSave
      draft={{ ...draft, ...overrides }}
      isBusy={false}
      isModeLocked={isModeLocked}
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

describe("PlayConfigPanel session mode picker", () => {
  it("shows chat selected for a default draft", () => {
    renderPanel();

    expect(screen.getByTestId("session-mode-trigger")).toHaveTextContent(
      "Chat (single agent)"
    );
  });

  it("reports an orchestrated choice on the draft", async () => {
    const { onDraftChange } = renderPanel();

    await userEvent.click(screen.getByTestId("session-mode-trigger"));
    await userEvent.click(
      await screen.findByRole("option", {
        name: "Orchestrated (agent per player)",
      })
    );

    expect(onDraftChange).toHaveBeenCalledWith(
      expect.objectContaining({ sessionMode: "orchestrated" })
    );
  });

  it("shows the mode a session is already running in", () => {
    renderPanel({ overrides: { sessionMode: "orchestrated" } });

    expect(screen.getByTestId("session-mode-trigger")).toHaveTextContent(
      "Orchestrated (agent per player)"
    );
  });

  it("is disabled with the reason once the session has run a prompt", () => {
    renderPanel({ isModeLocked: true });

    expect(screen.getByTestId("session-mode-trigger")).toBeDisabled();
    expect(
      screen.getByText("A session's mode is fixed once it has run a prompt.")
    ).toBeInTheDocument();
  });

  it("explains nothing about locking while the mode can still be changed", () => {
    renderPanel();

    expect(screen.getByTestId("session-mode-trigger")).not.toBeDisabled();
    expect(
      screen.queryByText("A session's mode is fixed once it has run a prompt.")
    ).not.toBeInTheDocument();
  });
});
