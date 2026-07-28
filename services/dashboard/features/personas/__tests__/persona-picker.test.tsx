import "@testing-library/jest-dom";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { PersonaPicker } from "@/features/personas/components/persona-picker";
import { installResizeObserver } from "@/features/shared/__tests__/heroui-test-env";
import { PersonaResponse } from "@/features/shared/lib/types";

const apiMocks = vi.hoisted(() => ({
  listPersonas: vi.fn(),
}));

vi.mock("@/features/play/lib/client-api", () => apiMocks);

beforeAll(installResizeObserver);

function persona(overrides: Partial<PersonaResponse> = {}): PersonaResponse {
  return {
    name: "rules-lawyer",
    display_name: "Rules Lawyer",
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
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.listPersonas.mockResolvedValue([]);
});

describe("PersonaPicker", () => {
  it("renders nothing when no personas are defined", async () => {
    const { container } = render(<PersonaPicker value="" onChange={vi.fn()} />);

    await waitFor(() => expect(apiMocks.listPersonas).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the catalogue cannot be loaded", async () => {
    apiMocks.listPersonas.mockRejectedValue(new Error("down"));

    const { container } = render(<PersonaPicker value="" onChange={vi.fn()} />);

    await waitFor(() => expect(apiMocks.listPersonas).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("offers each persona plus an explicit no-persona option", async () => {
    apiMocks.listPersonas.mockResolvedValue([
      persona(),
      persona({ name: "deck-builder", display_name: null }),
    ]);

    render(<PersonaPicker value="" onChange={vi.fn()} />);

    const trigger = await screen.findByTestId("subagent-persona-trigger");
    await userEvent.click(trigger);

    expect(
      await screen.findByRole("option", {
        name: /No persona \(subagents copy this session\)/i,
      })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "rules-lawyer — Rules Lawyer" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "deck-builder" })
    ).toBeInTheDocument();
  });

  it("reports the persona a user picks", async () => {
    apiMocks.listPersonas.mockResolvedValue([persona()]);
    const onChange = vi.fn();

    render(<PersonaPicker value="" onChange={onChange} />);

    await userEvent.click(
      await screen.findByTestId("subagent-persona-trigger")
    );
    await userEvent.click(
      await screen.findByRole("option", { name: "rules-lawyer — Rules Lawyer" })
    );

    expect(onChange).toHaveBeenCalledWith("rules-lawyer");
  });

  it("keeps a session's persisted choice listed even before the catalogue arrives", async () => {
    // Selecting a session must never silently clear the persona it is pinned to.
    render(<PersonaPicker value="rules-lawyer" onChange={vi.fn()} />);

    const trigger = await screen.findByTestId("subagent-persona-trigger");
    await userEvent.click(trigger);

    expect(
      await screen.findByRole("option", { name: "rules-lawyer" })
    ).toBeInTheDocument();
  });

  it("lets the user clear the choice back to no persona", async () => {
    apiMocks.listPersonas.mockResolvedValue([persona()]);
    const onChange = vi.fn();

    render(<PersonaPicker value="rules-lawyer" onChange={onChange} />);

    await userEvent.click(
      await screen.findByTestId("subagent-persona-trigger")
    );
    await userEvent.click(
      await screen.findByRole("option", {
        name: /No persona \(subagents copy this session\)/i,
      })
    );

    expect(onChange).toHaveBeenCalledWith("");
  });
});
