import { expect, test } from "@playwright/test";

test("renders an automatically continued turn in the play transcript", async ({
  page,
}) => {
  const sessionId = "session-continuation";
  const jobId = "job-continuation";
  let promptSubmitted = false;
  const timestamp = "2026-05-11T00:00:00.000Z";

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
    recent_job: null,
    recent_jobs: [],
  };

  const job = {
    id: jobId,
    prompt: "continue the response",
    metadata: {},
    status: promptSubmitted ? "running" : "queued",
    attempts: 1,
    max_attempts: 1,
    error_code: null,
    error_message: null,
    result_text: null,
    cancellation_requested_at: null,
    created_at: timestamp,
    started_at: timestamp,
    completed_at: null,
    latest_event_id: null,
    latest_event_type: null,
    outputs: [],
    events: [],
    available_tools: [],
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
      await json({ sessions: [{ ...session, recent_job: null }] });
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
      await json({ jobs: [], page: { limit: 100, offset: 0, total: 0 } });
      return;
    }
    if (
      path === `/api/proxy/orchestrator/sessions/${sessionId}/prompts` &&
      request.method() === "POST"
    ) {
      promptSubmitted = true;
      await json({ job: { ...job, status: "running" } }, 202);
      return;
    }
    if (path === `/api/proxy/orchestrator/jobs/${jobId}`) {
      await json({
        job: { ...job, status: promptSubmitted ? "running" : "queued" },
      });
      return;
    }
    if (path === `/api/proxy/orchestrator/jobs/${jobId}/events/stream`) {
      const events = [
        {
          id: "event-model-a",
          event_type: "model_output",
          payload: { text: "SEGMENT_A" },
          created_at: "2026-05-11T00:00:01.000Z",
        },
        {
          id: "event-continuation",
          event_type: "turn_continued",
          payload: {
            reason: "output_token_limit",
            finish_reason: "length",
            continuation: 1,
            max_continuations: 3,
          },
          created_at: "2026-05-11T00:00:02.000Z",
        },
        {
          id: "event-model-b",
          event_type: "model_output",
          payload: { text: "SEGMENT_B" },
          created_at: "2026-05-11T00:00:03.000Z",
        },
        {
          id: "event-completion",
          event_type: "completion",
          payload: { text: "SEGMENT_ASEGMENT_B" },
          created_at: "2026-05-11T00:00:04.000Z",
        },
      ];
      const body = events
        .map(
          (event) =>
            `id: ${event.id}\nevent: ${event.event_type}\ndata: ${JSON.stringify(event)}\n\n`,
        )
        .join("");
      await route.fulfill({
        status: 200,
        headers: {
          "cache-control": "no-cache",
          "content-type": "text/event-stream",
        },
        body,
      });
      return;
    }

    throw new Error(
      `Unhandled orchestrator smoke route: ${request.method()} ${path}`,
    );
  });

  await page.goto("/play");
  await expect(page.getByTestId("play-prompt-input")).toBeEnabled();
  await page.getByTestId("play-prompt-input").fill("continue the response");
  await page.getByTestId("play-prompt-send").click();

  await expect(page.getByTestId("play-job-state")).toHaveText("Completed");
  await expect(page.getByTestId("play-turn-continued")).toContainText(
    "turn continued automatically",
  );
  await expect(page.getByTestId("play-turn-continued")).toContainText("length");
  await expect(page.getByTestId("play-turn-continued")).toContainText(
    "continuation 1 of 3",
  );
  await expect(page.getByText("SEGMENT_A", { exact: true })).toBeVisible();
  await expect(
    page.getByText("SEGMENT_ASEGMENT_B", { exact: true }),
  ).toBeVisible();
});
