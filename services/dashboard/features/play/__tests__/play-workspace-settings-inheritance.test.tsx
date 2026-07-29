import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import {
  getApi,
  renderPlayWorkspace,
  resetPlayWorkspaceEnvironment,
  sessionSummary,
} from "@/features/play/__tests__/play-workspace-test-support";
import { SessionDraft } from "@/features/shared/lib/types";

const api = getApi();

/**
 * A configuration the user committed in an earlier visit. `anthropic` is one of
 * the providers in the test catalogue, so it survives validation; the model is
 * deliberately one the provider no longer offers.
 */
const storedDraft: Omit<SessionDraft, "name"> & { name: string } = {
  name: "",
  providerId: "anthropic",
  modelName: "claude-2-retired",
  recentMessageLimit: "7",
  recentToolExchangeLimit: "3",
  reasoning: { enabled: true, effort: "high", maxTokens: "1024" },
  gatewayOptionsText: '{"temperature":0.4}',
  providerOptionsText: "{}",
  selectedSkills: ["skill-b"],
  defaultSubagentPersona: "",
  sessionMode: "chat",
};

function storeLastUsedDraft(overrides: Partial<SessionDraft> = {}) {
  globalThis.localStorage.setItem(
    "play:lastUsedDraft",
    JSON.stringify({ ...storedDraft, ...overrides })
  );
}

describe("PlayWorkspace settings inheritance", () => {
  beforeEach(() => {
    resetPlayWorkspaceEnvironment();
  });

  it("starts a fresh visit from the last-used settings instead of the defaults", async () => {
    storeLastUsedDraft();
    // No sessions, so nothing overwrites the seeded draft.
    api.listSessions.mockResolvedValue([]);

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("draft-provider")).toHaveTextContent(
        "anthropic"
      )
    );
    // The stale model is clamped to one the provider still offers rather than
    // being carried through blindly.
    expect(screen.getByTestId("draft-model")).toHaveTextContent(
      "claude-3-5-haiku"
    );
    expect(screen.getByTestId("draft-skills")).toHaveTextContent("skill-b");
    expect(screen.getByTestId("draft-reasoning")).toHaveTextContent(
      "true:high"
    );
    expect(screen.getByTestId("draft-gateway-options")).toHaveTextContent(
      '{"temperature":0.4}'
    );
    expect(screen.getByTestId("draft-message-limit")).toHaveTextContent("7");
  });

  it("falls back to the configuration defaults when nothing was stored", async () => {
    api.listSessions.mockResolvedValue([]);

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("draft-provider")).toHaveTextContent("openai")
    );
    expect(screen.getByTestId("draft-skills")).toHaveTextContent("skill-a");
  });

  it("does not override the settings of a session the user opened", async () => {
    storeLastUsedDraft();
    api.listSessions.mockResolvedValue([sessionSummary]);

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("selected-session-name")).toHaveTextContent(
        "Existing session"
      )
    );
    // The opened session is configured for openai/gpt-4o-mini and has no
    // skills; the stored preference must not bleed into it.
    await waitFor(() =>
      expect(screen.getByTestId("draft-provider")).toHaveTextContent("openai")
    );
    expect(screen.getByTestId("draft-model")).toHaveTextContent("gpt-4o-mini");
    expect(screen.getByTestId("draft-skills")).toHaveTextContent("");
  });

  it("remembers the settings a newly created session was given", async () => {
    api.listSessions.mockResolvedValue([]);

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("draft-provider")).toHaveTextContent("openai")
    );
    // Move the draft off the defaults, then create a session with it.
    fireEvent.click(screen.getByRole("button", { name: /change provider/i }));
    fireEvent.click(screen.getByRole("button", { name: /create session/i }));

    await waitFor(() => expect(api.createSession).toHaveBeenCalled());
    await waitFor(() => {
      const stored = globalThis.localStorage.getItem("play:lastUsedDraft");
      expect(stored).not.toBeNull();
      expect(JSON.parse(stored as string)).toEqual(
        expect.objectContaining({
          providerId: "anthropic",
          modelName: "claude-3-5-haiku",
          // The name is never carried into the next session.
          name: "",
        })
      );
    });
  });
});
