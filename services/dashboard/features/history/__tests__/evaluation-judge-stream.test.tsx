import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { useState } from "react";

import { EvaluationControl } from "@/features/history/components/evaluation-control";
import {
  JudgeDraft,
  createDefaultJudgeDraft,
} from "@/features/history/lib/judge-config";
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

afterEach(() => {
  vi.clearAllMocks();
});

describe("EvaluationControl judge config", () => {
  it("assembles the judge object from selected provider/model/reasoning/skills/prompt", async () => {
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
    fireEvent.change(screen.getByTestId("judge-provider"), {
      target: { value: "anthropic" },
    });
    // Enable reasoning + effort high.
    fireEvent.click(screen.getByTestId("judge-reasoning-enabled"));
    fireEvent.change(screen.getByTestId("judge-reasoning-effort"), {
      target: { value: "high" },
    });
    fireEvent.change(screen.getByTestId("judge-reasoning-max-tokens"), {
      target: { value: "2048" },
    });
    // Custom prompt + skill.
    fireEvent.change(screen.getByTestId("judge-prompt"), {
      target: { value: "be strict" },
    });
    fireEvent.click(screen.getByTestId("judge-skill-core-rules"));

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
