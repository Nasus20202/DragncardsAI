import "@testing-library/jest-dom";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { JudgeConfigPanel } from "@/features/history/components/judge-config";
import { installResizeObserver } from "@/features/shared/__tests__/heroui-test-env";
import { JudgeDraft } from "@/features/history/lib/judge-config";
import { ProviderResponse } from "@/features/shared/lib/types";

const PROVIDERS: ProviderResponse[] = [
  {
    provider_id: "openrouter",
    model_prefix: "openrouter",
    models: [
      "anthropic/claude-sonnet-4",
      "anthropic/claude-haiku-4",
      "openai/gpt-5",
      "openai/gpt-5-mini",
    ],
    available: true,
    error: null,
  },
];

function draft(overrides: Partial<JudgeDraft> = {}): JudgeDraft {
  return {
    providerId: "openrouter",
    modelName: "openai/gpt-5",
    reasoningEnabled: false,
    reasoningEffort: "medium",
    reasoningMaxTokens: "",
    promptOverride: "",
    selectedSkills: [],
    ...overrides,
  };
}

beforeAll(installResizeObserver);

describe("JudgeConfigPanel model picker", () => {
  it("narrows the provider's model catalogue as the judge model is searched", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(
      <JudgeConfigPanel
        draft={draft()}
        providers={PROVIDERS}
        skills={[]}
        onChange={onChange}
      />
    );

    const input = screen.getByTestId("judge-model");
    expect(input).toHaveValue("openai/gpt-5");

    await user.click(input);
    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(4));

    await user.keyboard("sonnet");

    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(1));
    await user.click(
      screen.getByRole("option", { name: "anthropic/claude-sonnet-4" })
    );

    expect(onChange).toHaveBeenCalledWith(
      draft({ modelName: "anthropic/claude-sonnet-4" })
    );
  });

  it("keeps a drafted model the provider does not offer selectable", async () => {
    const user = userEvent.setup();

    render(
      <JudgeConfigPanel
        draft={draft({ modelName: "legacy/retired-model" })}
        providers={PROVIDERS}
        skills={[]}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByTestId("judge-model")).toHaveValue(
      "legacy/retired-model"
    );

    await user.click(screen.getByTestId("judge-model"));
    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(5));
    expect(
      screen.getByRole("option", { name: "legacy/retired-model" })
    ).toBeInTheDocument();
  });

  it("disables the model search when the provider exposes no models", () => {
    render(
      <JudgeConfigPanel
        draft={draft({ modelName: "" })}
        providers={[]}
        skills={[]}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByTestId("judge-model")).toBeDisabled();
  });
});
