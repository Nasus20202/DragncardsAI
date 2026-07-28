import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import {
  getApi,
  providers,
  renderPlayWorkspace,
  resetPlayWorkspaceEnvironment,
} from "@/features/play/__tests__/play-workspace-test-support";
import type { ProviderResponse } from "@/features/shared/lib/types";

const api = getApi();

/** A promise the test resolves by hand, to hold `/providers` in flight. */
function createDeferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

describe("PlayWorkspace initial loading", () => {
  beforeEach(() => {
    resetPlayWorkspaceEnvironment();
  });

  it("surfaces a visible error when the sessions fetch fails", async () => {
    api.listSessions.mockRejectedValue(new Error("sessions down"));

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("error-text")).toHaveTextContent(
        /failed to load sessions/i
      )
    );
  });

  it("surfaces a visible error when the skills fetch fails", async () => {
    api.listAvailableSkills.mockRejectedValue(new Error("skills down"));

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("error-text")).toHaveTextContent(
        /failed to load skills/i
      )
    );
  });

  it("combines the message when both sessions and skills fail", async () => {
    api.listSessions.mockRejectedValue(new Error("sessions down"));
    api.listAvailableSkills.mockRejectedValue(new Error("skills down"));

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("error-text")).toHaveTextContent(
        /failed to load sessions and skills/i
      )
    );
  });

  it("renders the workspace without waiting for the provider catalog", async () => {
    const pending = createDeferred<ProviderResponse[]>();
    api.listProviders.mockReturnValue(pending.promise);

    renderPlayWorkspace();

    // The workspace is fully rendered and Ready while `/providers` is still
    // in flight — a slow gateway probe must never gate the first paint.
    await waitFor(() =>
      expect(screen.getByTestId("play-workspace")).toBeInTheDocument()
    );
    expect(screen.getByTestId("status-text")).toHaveTextContent("Ready");
    expect(screen.getByTestId("provider-count")).toHaveTextContent("0");

    // The catalog is applied once it eventually arrives.
    pending.resolve(providers);
    await waitFor(() =>
      expect(screen.getByTestId("provider-count")).toHaveTextContent("2")
    );
  });

  it("defaults the selectors to a working provider once the catalog arrives", async () => {
    api.listSessions.mockResolvedValue([]);
    const pending = createDeferred<ProviderResponse[]>();
    api.listProviders.mockReturnValue(pending.promise);

    renderPlayWorkspace();

    // Before the catalog lands the draft holds the configuration defaults.
    await waitFor(() =>
      expect(screen.getByTestId("draft-provider")).toHaveTextContent("openai")
    );

    pending.resolve([
      {
        provider_id: "openai",
        model_prefix: "openai",
        models: [],
        available: false,
        error: "no API key configured",
      },
      {
        provider_id: "anthropic",
        model_prefix: "anthropic",
        models: ["claude-3-5-haiku"],
        available: true,
        error: null,
      },
    ]);

    await waitFor(() =>
      expect(screen.getByTestId("draft-provider")).toHaveTextContent(
        "anthropic"
      )
    );
    expect(screen.getByTestId("draft-model")).toHaveTextContent(
      "claude-3-5-haiku"
    );
    expect(screen.getByTestId("providers-notice")).toHaveTextContent(
      /no models available from openai/i
    );
  });

  it("names providers that answer with an empty model list in the notice", async () => {
    api.listSessions.mockResolvedValue([]);
    // The state a missing API key produces: the listing succeeds, so the
    // provider reports itself available, but it offers nothing to select.
    api.listProviders.mockResolvedValue([
      {
        provider_id: "openai",
        model_prefix: "openai",
        models: [],
        available: true,
        error: null,
      },
      {
        provider_id: "anthropic",
        model_prefix: "anthropic",
        models: ["claude-3-5-haiku"],
        available: true,
        error: null,
      },
    ]);

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("providers-notice")).toHaveTextContent(
        /no models available from openai/i
      )
    );
    // The working provider is not named, and it is what the selectors default to.
    expect(screen.getByTestId("providers-notice")).not.toHaveTextContent(
      "anthropic,"
    );
    expect(screen.getByTestId("draft-provider")).toHaveTextContent("anthropic");
  });

  it("shows no notice when every provider offers models", async () => {
    api.listSessions.mockResolvedValue([]);

    renderPlayWorkspace();

    await waitFor(() =>
      expect(screen.getByTestId("draft-provider")).toHaveTextContent("openai")
    );
    expect(screen.queryByTestId("providers-notice")).toBeNull();
  });

  it("keeps providers degradation graceful without a fatal error", async () => {
    api.listProviders.mockRejectedValue(new Error("providers down"));

    renderPlayWorkspace();

    // Providers failing shows a non-blocking notice, not the fatal error text.
    await waitFor(() =>
      expect(screen.getByTestId("providers-notice")).toBeInTheDocument()
    );
    expect(screen.getByTestId("error-text")).toHaveTextContent("");
  });
});
