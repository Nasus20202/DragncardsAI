import "@testing-library/jest-dom";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { PlayConfigPanel } from "@/features/play/components/play-config-panel";
import { installResizeObserver } from "@/features/shared/__tests__/heroui-test-env";
import { ProviderResponse, SessionDraft } from "@/features/shared/lib/types";

beforeAll(installResizeObserver);

/**
 * The shape a real deployment produces when only some providers have API keys:
 * the model listing succeeds for every provider (so `available` stays true) but
 * comes back empty for the ones without a key.
 */
const degradedProviders: ProviderResponse[] = [
  {
    provider_id: "openrouter",
    model_prefix: "openrouter",
    models: ["openrouter/free", "openrouter/paid"],
    available: true,
    error: null,
  },
  {
    provider_id: "openai",
    model_prefix: "openai",
    models: [],
    available: true,
    error: null,
  },
  {
    provider_id: "lmstudio",
    model_prefix: "lmstudio",
    models: [],
    available: false,
    error: "Timed out while listing models",
  },
];

function draftFor(providerId: string, modelName: string): SessionDraft {
  return {
    name: "Session",
    providerId,
    modelName,
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
}

function renderPanel(draft: SessionDraft, modelOptions: string[]) {
  const onDraftChange = vi.fn();
  render(
    <PlayConfigPanel
      canSave
      draft={draft}
      isBusy={false}
      isOpen
      mcps={[]}
      modelOptions={modelOptions}
      providers={degradedProviders}
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

describe("PlayConfigPanel with a degraded provider catalogue", () => {
  it("labels providers that expose no models and refuses to select them", async () => {
    const user = userEvent.setup();
    renderPanel(draftFor("openrouter", "openrouter/free"), [
      "openrouter/free",
      "openrouter/paid",
    ]);

    await user.click(screen.getByRole("button", { name: /Provider$/ }));

    const usable = await screen.findByRole("option", { name: "openrouter" });
    expect(usable).not.toHaveAttribute("aria-disabled", "true");
    for (const providerId of ["openai", "lmstudio"]) {
      const option = screen.getByRole("option", {
        name: `${providerId} (no models)`,
      });
      expect(option).toHaveAttribute("aria-disabled", "true");
    }
  });

  it("still lets the user move to a provider that works", async () => {
    const user = userEvent.setup();
    // A session pinned to a provider whose key has since gone missing.
    const { onDraftChange } = renderPanel(draftFor("openai", "openai/gpt"), []);

    await user.click(screen.getByRole("button", { name: /Provider$/ }));
    await user.click(await screen.findByRole("option", { name: "openrouter" }));

    await waitFor(() =>
      expect(onDraftChange).toHaveBeenCalledWith(
        expect.objectContaining({ providerId: "openrouter" })
      )
    );
  });

  it("keeps the model picker usable for a working provider", async () => {
    const user = userEvent.setup();
    const { onDraftChange } = renderPanel(
      draftFor("openrouter", "openrouter/free"),
      ["openrouter/free", "openrouter/paid"]
    );

    const modelInput = screen.getByRole("combobox", { name: "Model" });
    expect(modelInput).not.toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Show suggestions" }));
    await user.click(
      await screen.findByRole("option", { name: "openrouter/paid" })
    );

    await waitFor(() =>
      expect(onDraftChange).toHaveBeenCalledWith(
        expect.objectContaining({ modelName: "openrouter/paid" })
      )
    );
  });
});
