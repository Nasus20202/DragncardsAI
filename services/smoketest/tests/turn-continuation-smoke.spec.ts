import { expect, test } from "@playwright/test";

const sessionId = "session-continuation";
const parentJobId = "job-continuation";
const childJobId = "job-subagent";
const timestamp = "2026-08-29T00:00:00.000Z";

function event(
  id: string,
  eventType: string,
  payload: Record<string, unknown>,
  seconds: number,
) {
  return {
    id,
    event_type: eventType,
    payload,
    created_at: `2026-08-29T00:00:0${seconds}.000Z`,
  };
}

function summaryOf(job: Record<string, unknown>) {
  const {
    events: _events,
    outputs: _outputs,
    available_tools: _tools,
    ...summary
  } = job;
  return summary;
}

test("renders continuation seams in the Play transcript and subagent modal", async ({
  page,
}) => {
  const parentEvents = [
    event("parent-progress", "progress", { message: "Running" }, 1),
    event("parent-model-a", "model_output", { text: "PARENT_A" }, 2),
    event(
      "parent-continuation",
      "turn_continued",
      {
        reason: "output_token_limit",
        finish_reason: "length",
        continuation: 1,
        max_continuations: 3,
      },
      3,
    ),
    event("parent-model-b", "model_output", { text: "PARENT_B" }, 4),
    event(
      "parent-subagent-start",
      "subagent_started",
      {
        child_job_id: childJobId,
        child_session_id: "session-subagent",
        name: "Rules helper",
      },
      5,
    ),
    event(
      "parent-subagent-complete",
      "subagent_completed",
      {
        child_job_id: childJobId,
        child_session_id: "session-subagent",
        name: "Rules helper",
      },
      6,
    ),
    event("parent-completion", "completion", { text: "PARENT_APARENT_B" }, 7),
  ];
  const childEvents = [
    event("child-model-a", "model_output", { text: "CHILD_A" }, 1),
    event(
      "child-continuation",
      "turn_continued",
      {
        reason: "output_token_limit",
        finish_reason: "length",
        continuation: 1,
        max_continuations: 3,
      },
      2,
    ),
    event("child-model-b", "model_output", { text: "CHILD_B" }, 3),
    event("child-completion", "completion", { text: "CHILD_ACHILD_B" }, 4),
  ];
  const parentJob = {
    id: parentJobId,
    prompt: "continue the response",
    metadata: {},
    status: "completed",
    attempts: 1,
    max_attempts: 1,
    error_code: null,
    error_message: null,
    result_text: "PARENT_APARENT_B",
    cancellation_requested_at: null,
    created_at: timestamp,
    started_at: timestamp,
    completed_at: timestamp,
    latest_event_id: "parent-completion",
    latest_event_type: "completion",
    outputs: [],
    events: parentEvents,
    available_tools: [],
  };
  const parentSummary = summaryOf(parentJob);
  const session = {
    id: sessionId,
    name: "Continuation smoke session",
    status: "active",
    context_recent_message_limit: null,
    context_recent_tool_exchange_limit: null,
    metadata: {},
    created_at: timestamp,
    updated_at: timestamp,
    terminated_at: null,
    model_config: {
      provider_id: "smoke",
      model_name: "smoke-model",
      gateway_options: {},
      provider_options: {},
      updated_at: timestamp,
    },
    skills: [],
    mcps: [],
    players: [],
    recent_job: parentSummary,
    recent_jobs: [parentSummary],
  };

  await page.route("**/api/config", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        config: {
          appName: "Smoke",
          defaultProviderId: "smoke",
          defaultModelName: "smoke-model",
          defaultGameServiceMcpEnabled: false,
          defaultGameServiceMcpName: "game-service",
          defaultGameServiceMcpTransport: "streamable-http",
          defaultGameServiceMcpUrl: "http://game-service/mcp/",
          defaultSkills: [],
          defaultCustomMcps: [],
          dragncardsFrontendUrl: "http://localhost:3000",
          marvelLcgBaseUrl: "http://localhost:4006",
          bifrostUiUrl: "http://localhost:4003",
          defaultReasoningEnabled: false,
          defaultReasoningEffort: "medium",
        },
      }),
    });
  });

  await page.route("**/api/proxy/orchestrator/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const json = async (body: unknown, status = 200) => {
      await route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    };

    if (path === "/api/proxy/orchestrator/providers") {
      await json({
        providers: [
          {
            provider_id: "smoke",
            model_prefix: "smoke/",
            models: ["smoke-model"],
            available: true,
            error: null,
          },
        ],
      });
      return;
    }
    if (path === "/api/proxy/orchestrator/skills") {
      await json({ skills: [] });
      return;
    }
    if (path === "/api/proxy/orchestrator/personas") {
      await json({ personas: [] });
      return;
    }
    if (
      path === "/api/proxy/orchestrator/sessions" &&
      request.method() === "GET"
    ) {
      await json({ sessions: [session] });
      return;
    }
    if (path === `/api/proxy/orchestrator/sessions/${sessionId}`) {
      await json({ session });
      return;
    }
    if (path === `/api/proxy/orchestrator/sessions/${sessionId}/mcps`) {
      await json({ mcps: [] });
      return;
    }
    if (path === `/api/proxy/orchestrator/sessions/${sessionId}/context`) {
      await json({
        tokens_used: 0,
        context_window_size: 128000,
        usage_ratio: 0,
        compaction_count: 0,
        last_compacted_at: null,
        multi_turn_memory: true,
        token_breakdown: { system_prompt: 0, replay: 0, tools: 0 },
      });
      return;
    }
    if (path === `/api/proxy/orchestrator/sessions/${sessionId}/jobs`) {
      await json({
        jobs: [parentSummary],
        page: { limit: 100, offset: 0, total: 1 },
      });
      return;
    }
    if (path === `/api/proxy/orchestrator/jobs/${parentJobId}`) {
      await json({ job: parentJob });
      return;
    }
    if (path === `/api/proxy/orchestrator/jobs/${childJobId}/events`) {
      await json({ events: childEvents });
      return;
    }

    throw new Error(
      `Unhandled orchestrator continuation route: ${request.method()} ${path}`,
    );
  });

  await page.goto(`/play?session=${sessionId}`);
  await expect(page.getByTestId("play-job-state")).toHaveText("Completed");

  const transcriptMarker = page.getByTestId("play-turn-continued").first();
  await expect(transcriptMarker).toContainText("turn continued automatically");
  await expect(transcriptMarker).toContainText("length");
  await expect(transcriptMarker).toContainText("continuation 1 of 3");
  await expect(page.getByText("PARENT_A", { exact: true })).toBeVisible();
  await expect(
    page.getByText("PARENT_APARENT_B", { exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Expand subagents" }).click();
  await page.getByRole("button", { name: /Rules helper/ }).click();

  const modal = page.getByRole("dialog", { name: "Subagent output" });
  await expect(modal).toBeVisible();
  const modalMarker = modal.getByTestId("play-turn-continued");
  await expect(modalMarker).toContainText("turn continued automatically");
  await expect(modalMarker).toContainText("length");
  await expect(modalMarker).toContainText("continuation 1 of 3");
  await expect(modal.getByText("CHILD_A", { exact: true })).toBeVisible();
  await expect(
    modal.getByText("CHILD_ACHILD_B", { exact: true }),
  ).toBeVisible();
});
