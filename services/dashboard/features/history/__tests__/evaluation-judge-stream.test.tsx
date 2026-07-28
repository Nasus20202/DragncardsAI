import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";
import { useState } from "react";

import { EvaluationControl } from "@/features/history/components/evaluation-control";
import {
  JudgeDraft,
  createDefaultJudgeDraft,
} from "@/features/history/lib/judge-config";
import { installResizeObserver } from "@/features/shared/__tests__/heroui-test-env";
import { DashboardConfig, ProviderResponse } from "@/features/shared/lib/types";

const requestEvaluation = vi.fn();

vi.mock("@/features/history/lib/eval-api", () => ({
  requestEvaluation: (...args: unknown[]) => requestEvaluation(...args),
}));

const CONFIG: DashboardConfig = {
  appName: "Test",
  defaultProviderId: "openrouter",
  defaultModelName: "m1",
  defaultGameServiceMcpEnabled: true,
  defaultGameServiceMcpName: "game-service",
  defaultGameServiceMcpTransport: "streamable-http",
  defaultGameServiceMcpUrl: "http://localhost:4001/mcp/",
  defaultSkills: [],
  defaultCustomMcps: [],
  dragncardsFrontendUrl: "http://localhost:3000",
  bifrostUiUrl: "http://localhost:4003",
  defaultReasoningEnabled: false,
  defaultReasoningEffort: "medium",
};

const PROVIDERS: ProviderResponse[] = [
  {
    provider_id: "openrouter",
    model_prefix: "openrouter/",
    models: ["m1", "m2"],
    available: true,
    error: null,
  },
  {
    provider_id: "anthropic",
    model_prefix: "anthropic/",
    models: ["claude-x"],
    available: true,
    error: null,
  },
];

const SKILLS = [
  { name: "core-rules", path: "/s/core", description: "rules", metadata: {} },
];

/** Render the control with a controlled judge draft (mirrors the workspace). */
function ControlHarness({ initial }: { initial: JudgeDraft }) {
  const [draftState, setDraftState] = useState<JudgeDraft>(initial);
  return (
    <EvaluationControl
      gameId="g1"
      selectedSeq={12}
      judgeDraft={draftState}
      onJudgeDraftChange={setDraftState}
      providers={PROVIDERS}
      skills={SKILLS}
    />
  );
}

beforeAll(installResizeObserver);

afterEach(() => {
  vi.clearAllMocks();
});

/**
 * Open a HeroUI `Select` by its trigger test id and choose the option with the
 * given accessible name. HeroUI renders a listbox popover rather than a native
 * `<select>`, so the choice has to be clicked.
 */
async function chooseOption(
  user: ReturnType<typeof userEvent.setup>,
  triggerTestId: string,
  optionName: string
) {
  await user.click(screen.getByTestId(triggerTestId));
  await waitFor(() =>
    expect(screen.getByRole("option", { name: optionName })).toBeInTheDocument()
  );
  await user.click(screen.getByRole("option", { name: optionName }));
}

/**
 * Flip the switch inside the toggle row carrying the given test id. The row is a
 * HeroUI `Switch`, so the control to activate is the `switch` role within it.
 */
async function flipSwitch(
  user: ReturnType<typeof userEvent.setup>,
  testId: string
) {
  await user.click(within(screen.getByTestId(testId)).getByRole("switch"));
}

describe("EvaluationControl judge config", () => {
  it("assembles the judge object from selected provider/model/reasoning/skills/prompt", async () => {
    const user = userEvent.setup();
    requestEvaluation.mockResolvedValue({
      request_id: "req-1",
      game_id: "g1",
      scope: "move",
      created_count: 1,
      skipped_count: 0,
      targets: [
        { target_seq: 12, scope: "move", round_span: null, status: "pending" },
      ],
    });

    render(<ControlHarness initial={createDefaultJudgeDraft(CONFIG)} />);

    // Pick provider anthropic -> model clamps to claude-x.
    await chooseOption(user, "judge-provider", "anthropic");
    // Enable reasoning + effort high.
    await flipSwitch(user, "judge-reasoning-enabled");
    await chooseOption(user, "judge-reasoning-effort", "High");
    fireEvent.change(screen.getByTestId("judge-reasoning-max-tokens"), {
      target: { value: "2048" },
    });
    // Custom prompt + skill.
    fireEvent.change(screen.getByTestId("judge-prompt"), {
      target: { value: "be strict" },
    });
    await flipSwitch(user, "judge-skill-core-rules");

    fireEvent.click(screen.getByTestId("eval-submit"));

    await waitFor(() => {
      expect(requestEvaluation).toHaveBeenCalledWith("g1", {
        scope: "move",
        selection: { seqs: [12] },
        force: false,
        judge: {
          provider_id: "anthropic",
          model_name: "claude-x",
          reasoning: { enabled: true, effort: "high", max_tokens: 2048 },
          prompt_override: "be strict",
          skills: ["core-rules"],
        },
      });
    });

    // Submitting enqueues the request and surfaces the queue confirmation.
    expect(await screen.findByTestId("eval-enqueued")).toBeInTheDocument();
  });
});
