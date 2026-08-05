import "@testing-library/jest-dom";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
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

/**
 * The message a field is currently reporting, reached the way a screen reader
 * reaches it: through the control's own `aria-describedby`. Asserting the
 * wiring and reading the text are the same act, so a message that is only
 * visually red cannot pass.
 */
function fieldError(inputTestId: string): HTMLElement {
  const control = screen.getByTestId(inputTestId);
  expect(control).toHaveAttribute("aria-invalid", "true");
  const describedBy = control.getAttribute("aria-describedby");
  expect(describedBy).toBeTruthy();
  const message = document.getElementById(describedBy as string);
  expect(message).not.toBeNull();
  return message as HTMLElement;
}

function expectNoFieldError(inputTestId: string) {
  const control = screen.getByTestId(inputTestId);
  expect(control).not.toHaveAttribute("aria-invalid");
  expect(control).not.toHaveAttribute("aria-describedby");
}

const nameError = () => fieldError("persona-name-input");
const promptError = () => fieldError("persona-prompt-input");

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

  it("blocks a save whose prompt is over the limit and says why", async () => {
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

    expect(promptError()).toHaveTextContent(String(MAX_PERSONA_PROMPT_CHARS));

    fireEvent.click(screen.getByRole("button", { name: /save persona/i }));

    await waitFor(() =>
      expect(promptError()).toHaveTextContent(String(MAX_PERSONA_PROMPT_CHARS))
    );
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

  it("does not pre-mark an untouched new-persona form as wrong", async () => {
    render(<PersonaEditor />);
    await waitFor(() =>
      expect(screen.getByTestId("personas-empty")).toBeInTheDocument()
    );

    expectNoFieldError("persona-name-input");
    expectNoFieldError("persona-prompt-input");
    expect(
      screen.queryByTestId("persona-save-problem")
    ).not.toBeInTheDocument();
  });

  it("states the missing name at the name field when an empty form is saved", async () => {
    render(<PersonaEditor />);
    await waitFor(() =>
      expect(screen.getByTestId("personas-empty")).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole("button", { name: /save persona/i }));

    await waitFor(() => expect(nameError()).toHaveTextContent(/needs a name/i));
    expect(apiMocks.savePersona).not.toHaveBeenCalled();
  });

  it("repeats the reason a refused save did nothing beside the button", async () => {
    render(<PersonaEditor />);
    await waitFor(() =>
      expect(screen.getByTestId("personas-empty")).toBeInTheDocument()
    );

    const button = screen.getByRole("button", { name: /save persona/i });
    fireEvent.click(button);

    // The button is a scroll away from the fields, so a press that does
    // nothing has to say why where the press happened -- and say it to a
    // screen reader through the button's own description.
    const summary = await screen.findByTestId("persona-save-problem");
    expect(summary).toHaveTextContent(/needs a name/i);
    expect(button).toHaveAttribute("aria-describedby", summary.id);

    fireEvent.change(screen.getByTestId("persona-name-input"), {
      target: { value: "rules-lawyer" },
    });
    fireEvent.change(screen.getByTestId("persona-prompt-input"), {
      target: { value: "Answer only from the printed rules." },
    });

    await waitFor(() =>
      expect(
        screen.queryByTestId("persona-save-problem")
      ).not.toBeInTheDocument()
    );
    expect(button).not.toHaveAttribute("aria-describedby");
  });

  it("states a malformed name at the name field while it is typed", async () => {
    render(<PersonaEditor />);
    await waitFor(() =>
      expect(screen.getByTestId("personas-empty")).toBeInTheDocument()
    );

    fireEvent.change(screen.getByTestId("persona-name-input"), {
      target: { value: "Rules Lawyer" },
    });

    expect(nameError()).toHaveTextContent(/lowercase/i);
    // A name problem is not reported against the prompt as well.
    expect(promptError()).toHaveTextContent(/system prompt/i);
    expect(nameError().id).not.toEqual(promptError().id);
  });

  it("states a missing system prompt at the prompt field", async () => {
    render(<PersonaEditor />);
    await waitFor(() =>
      expect(screen.getByTestId("personas-empty")).toBeInTheDocument()
    );

    fireEvent.change(screen.getByTestId("persona-name-input"), {
      target: { value: "rules-lawyer" },
    });

    expectNoFieldError("persona-name-input");
    expect(promptError()).toHaveTextContent(/system prompt/i);
  });

  it("states a problem on the edit path too, not only when creating", async () => {
    apiMocks.listPersonas.mockResolvedValue([persona()]);

    render(<PersonaEditor />);
    await waitFor(() =>
      expect(screen.getByTestId("personas-list")).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole("button", { name: /edit rules-lawyer/i }));
    // A persona loaded for editing is valid, so nothing is marked until it is
    // made invalid.
    expectNoFieldError("persona-prompt-input");

    fireEvent.change(screen.getByTestId("persona-prompt-input"), {
      target: { value: "   " },
    });

    expect(promptError()).toHaveTextContent(/system prompt/i);

    fireEvent.click(screen.getByRole("button", { name: /save persona/i }));

    await waitFor(() =>
      expect(screen.getByTestId("persona-save-problem")).toHaveTextContent(
        /system prompt/i
      )
    );
    expect(apiMocks.savePersona).not.toHaveBeenCalled();
  });
});

describe("PersonaEditor server rendering", () => {
  it("renders a save button carrying no disabled attribute", () => {
    // DRA-49: the save button's `disabled` was the one attribute the server
    // markup and the hydrating client disagreed about, and React does not
    // patch such a disagreement up -- it leaves the live button's disabled
    // state divergent from what the component rendered. Nothing can disagree
    // about an attribute that is not emitted, which is what keeping validity
    // out of `isDisabled` buys.
    const markup = renderToStaticMarkup(<PersonaEditor />);
    const saveButton = markup
      .split("<button")
      .find((tag) => tag.includes('aria-label="Save persona"'));

    expect(saveButton).toBeDefined();
    expect(saveButton).not.toMatch(/\sdisabled(=|\s|>)/);
    expect(saveButton).not.toMatch(/data-disabled/);
  });
});
