import "@testing-library/jest-dom";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { JudgeConfigPanel } from "@/features/history/components/judge-config";
import { installResizeObserver } from "@/features/shared/__tests__/heroui-test-env";
import { JudgeDraft } from "@/features/history/lib/judge-config";
import {
  ProviderResponse,
  SkillDefinitionResponse,
} from "@/features/shared/lib/types";

const PROVIDERS: ProviderResponse[] = [
  {
    provider_id: "openrouter",
    model_prefix: "openrouter",
    models: ["openai/gpt-5", "openai/gpt-5-mini"],
    available: true,
    error: null,
  },
  {
    provider_id: "anthropic",
    model_prefix: "anthropic",
    models: ["claude-sonnet-4"],
    available: false,
    error: "no key",
  },
];

const SKILLS: SkillDefinitionResponse[] = [
  {
    name: "core-rules",
    path: "/s/core",
    description: "The Marvel Champions rules reference.",
    metadata: { version: "2" },
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

describe("JudgeConfigPanel fields", () => {
  it("renders reasoning and each skill as a switch on its keyed toggle row", () => {
    render(
      <JudgeConfigPanel
        draft={draft({ selectedSkills: ["core-rules"] })}
        providers={PROVIDERS}
        skills={SKILLS}
        onChange={vi.fn()}
      />
    );

    const reasoningRow = screen.getByTestId("judge-reasoning-enabled");
    expect(
      within(reasoningRow).getByRole("switch", { name: "Reasoning" })
    ).not.toBeChecked();

    expect(screen.getByTestId("judge-skills")).toBeInTheDocument();
    const skillRow = screen.getByTestId("judge-skill-core-rules");
    expect(
      within(skillRow).getByRole("switch", { name: "core-rules" })
    ).toBeChecked();
  });

  it("gives a described skill an info trigger and a bare one none", () => {
    render(
      <JudgeConfigPanel
        draft={draft()}
        providers={PROVIDERS}
        skills={[
          ...SKILLS,
          { name: "bare", path: "/s/bare", description: "", metadata: {} },
        ]}
        onChange={vi.fn()}
      />
    );

    // The judge panel used to drop skill descriptions entirely (only the name
    // reached a native `title`); it now carries Play's info trigger.
    expect(
      screen.getByRole("button", { name: "Info about core-rules" })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Info about bare" })
    ).not.toBeInTheDocument();
  });

  it("clamps the model to the newly-selected provider's catalogue", async () => {
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

    await user.click(screen.getByTestId("judge-provider"));
    await waitFor(() =>
      expect(
        screen.getByRole("option", { name: "anthropic (unavailable)" })
      ).toBeInTheDocument()
    );
    await user.click(
      screen.getByRole("option", { name: "anthropic (unavailable)" })
    );

    expect(onChange).toHaveBeenCalledWith(
      draft({ providerId: "anthropic", modelName: "claude-sonnet-4" })
    );
  });

  it("disables every control when the panel is disabled", () => {
    render(
      <JudgeConfigPanel
        draft={draft({ reasoningEnabled: true })}
        providers={PROVIDERS}
        skills={SKILLS}
        disabled
        onChange={vi.fn()}
      />
    );

    expect(screen.getByTestId("judge-provider")).toBeDisabled();
    expect(screen.getByTestId("judge-model")).toBeDisabled();
    expect(screen.getByTestId("judge-reasoning-effort")).toBeDisabled();
    expect(screen.getByTestId("judge-reasoning-max-tokens")).toBeDisabled();
    expect(screen.getByTestId("judge-prompt")).toBeDisabled();
    expect(
      within(screen.getByTestId("judge-reasoning-enabled")).getByRole("switch")
    ).toBeDisabled();
    expect(
      within(screen.getByTestId("judge-skill-core-rules")).getByRole("switch")
    ).toBeDisabled();
  });
});
