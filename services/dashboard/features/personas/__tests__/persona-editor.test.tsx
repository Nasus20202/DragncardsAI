import "@testing-library/jest-dom";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { PersonaEditor } from "@/features/personas/components/persona-editor";
import { MAX_PERSONA_PROMPT_CHARS } from "@/features/personas/lib/personas";
import { installResizeObserver } from "@/features/shared/__tests__/heroui-test-env";
import { PersonaResponse } from "@/features/shared/lib/types";

const apiMocks = vi.hoisted(() => ({
  listPersonas: vi.fn(),
  savePersona: vi.fn(),
  deletePersona: vi.fn(),
  listProviders: vi.fn(),
  listAvailableSkills: vi.fn(),
}));

vi.mock("@/features/play/lib/client-api", () => apiMocks);

beforeAll(installResizeObserver);

function persona(overrides: Partial<PersonaResponse> = {}): PersonaResponse {
  return {
    name: "rules-lawyer",
    display_name: "Rules Lawyer",
    description: "Checks rule interactions.",
    system_prompt: "Answer only from the printed rules.",
    provider_id: null,
    model_name: null,
    reasoning: null,
    skills: null,
    allowed_tools: null,
    gateway_options: {},
    provider_options: {},
    created_at: "2026-07-28T00:00:00Z",
    updated_at: "2026-07-28T00:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.listPersonas.mockResolvedValue([]);
  apiMocks.listProviders.mockResolvedValue([]);
  apiMocks.listAvailableSkills.mockResolvedValue([]);
  apiMocks.savePersona.mockImplementation(async (name: string) =>
    persona({ name })
  );
  apiMocks.deletePersona.mockResolvedValue(undefined);
});

describe("PersonaEditor", () => {
  it("states plainly that no personas are defined", async () => {
    render(<PersonaEditor />);

    await waitFor(() =>
      expect(screen.getByTestId("personas-empty")).toBeInTheDocument()
    );
    expect(screen.queryByTestId("personas-list")).not.toBeInTheDocument();
  });

  it("lists the personas that exist with their descriptions", async () => {
    apiMocks.listPersonas.mockResolvedValue([
      persona(),
      persona({
        name: "deck-builder",
        display_name: null,
        description: "Builds decklists.",
      }),
    ]);

    render(<PersonaEditor />);

    await waitFor(() =>
      expect(screen.getByTestId("personas-list")).toBeInTheDocument()
    );
    expect(screen.getByText(/rules-lawyer — Rules Lawyer/)).toBeInTheDocument();
    expect(screen.getByText("Checks rule interactions.")).toBeInTheDocument();
    expect(screen.getByText("Builds decklists.")).toBeInTheDocument();
  });

  it("creates a persona from the form", async () => {
    render(<PersonaEditor />);
    await waitFor(() =>
      expect(screen.getByTestId("personas-empty")).toBeInTheDocument()
    );

    fireEvent.change(screen.getByTestId("persona-name-input"), {
      target: { value: "rules-lawyer" },
    });
    fireEvent.change(screen.getByTestId("persona-prompt-input"), {
      target: { value: "Answer only from the printed rules." },
    });
    fireEvent.click(screen.getByRole("button", { name: /save persona/i }));

    await waitFor(() =>
      expect(apiMocks.savePersona).toHaveBeenCalledWith("rules-lawyer", {
        system_prompt: "Answer only from the printed rules.",
        reasoning: { enabled: false },
      })
    );
    // The list is reloaded so the new persona appears without a page reload.
    expect(apiMocks.listPersonas).toHaveBeenCalledTimes(2);
  });

  it("populates the form from the persona being edited", async () => {
    apiMocks.listPersonas.mockResolvedValue([persona()]);

    render(<PersonaEditor />);
    await waitFor(() =>
      expect(screen.getByTestId("personas-list")).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole("button", { name: /edit rules-lawyer/i }));

    expect(screen.getByTestId("persona-name-input")).toHaveValue(
      "rules-lawyer"
    );
    expect(screen.getByTestId("persona-prompt-input")).toHaveValue(
      "Answer only from the printed rules."
    );
    // The name is the identity, so editing one is not a rename.
    expect(screen.getByTestId("persona-name-input")).toBeDisabled();
    expect(screen.getByText("Editing rules-lawyer")).toBeInTheDocument();
  });

  it("deletes a persona", async () => {
    apiMocks.listPersonas.mockResolvedValue([persona()]);

    render(<PersonaEditor />);
    await waitFor(() =>
      expect(screen.getByTestId("personas-list")).toBeInTheDocument()
    );

    apiMocks.listPersonas.mockResolvedValue([]);
    fireEvent.click(
      screen.getByRole("button", { name: /delete rules-lawyer/i })
    );

    await waitFor(() =>
      expect(apiMocks.deletePersona).toHaveBeenCalledWith("rules-lawyer")
    );
    await waitFor(() =>
      expect(screen.getByTestId("personas-empty")).toBeInTheDocument()
    );
  });

  it("blocks a save whose prompt is over the limit", async () => {
    render(<PersonaEditor />);
    await waitFor(() =>
      expect(screen.getByTestId("personas-empty")).toBeInTheDocument()
    );

    fireEvent.change(screen.getByTestId("persona-name-input"), {
      target: { value: "verbose" },
    });
    fireEvent.change(screen.getByTestId("persona-prompt-input"), {
      target: { value: "x".repeat(MAX_PERSONA_PROMPT_CHARS + 1) },
    });

    expect(screen.getByTestId("persona-prompt-over-limit")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /save persona/i })
    ).toBeDisabled();
    expect(apiMocks.savePersona).not.toHaveBeenCalled();
  });

  it("surfaces the orchestrator's rejection instead of discarding it", async () => {
    apiMocks.savePersona.mockRejectedValue(
      new Error("Unknown skill: no-such-skill")
    );

    render(<PersonaEditor />);
    await waitFor(() =>
      expect(screen.getByTestId("personas-empty")).toBeInTheDocument()
    );

    fireEvent.change(screen.getByTestId("persona-name-input"), {
      target: { value: "rules-lawyer" },
    });
    fireEvent.change(screen.getByTestId("persona-prompt-input"), {
      target: { value: "Answer from the rules." },
    });
    fireEvent.click(screen.getByRole("button", { name: /save persona/i }));

    await waitFor(() =>
      expect(
        screen.getByText("Unknown skill: no-such-skill")
      ).toBeInTheDocument()
    );
  });

  it("reports a failed load rather than showing an empty catalogue as fact", async () => {
    apiMocks.listPersonas.mockRejectedValue(new Error("orchestrator is down"));

    render(<PersonaEditor />);

    await waitFor(() =>
      expect(screen.getByText("orchestrator is down")).toBeInTheDocument()
    );
  });
});
