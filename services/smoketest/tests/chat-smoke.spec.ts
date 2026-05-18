import { expect, test } from "@playwright/test";

import {
  createGamePrompt,
  gameServiceBaseUrl,
  orchestratorBaseUrl,
} from "../src/config";
import {
  extractCreatedGameSessionId,
  logSmokeChatTranscript,
  logSmokeStatus,
  requireOk,
  requireSmokeEnvironment,
  waitForCreatedGameState,
  waitForCreatedSessionId,
  waitForLatestJob,
  waitForSessionSetup,
} from "../src/utils";
import type { JobEventsResponse, SessionListResponse } from "../src/types";

test("creates a Marvel Champions game from dashboard chat", async ({
  page,
  request,
}) => {
  await requireSmokeEnvironment(request);

  logSmokeStatus("capturing existing orchestrator sessions before the run");
  const existingSessionsResponse = await requireOk(
    request,
    `${orchestratorBaseUrl}/sessions`,
    "orchestrator sessions",
  );
  const existingSessionsPayload =
    (await existingSessionsResponse.json()) as SessionListResponse;
  const existingSessionIds = new Set(
    existingSessionsPayload.sessions.map((session) => session.id),
  );

  logSmokeStatus("opening dashboard play workspace");
  await page.goto("/play");

  logSmokeStatus("creating a new dashboard session");
  await page.getByTestId("new-session-button").click();

  const sessionId = await waitForCreatedSessionId(request, existingSessionIds);

  await expect
    .poll(
      () => {
        return new URL(page.url()).searchParams.get("session") ?? "";
      },
      { timeout: 15_000 },
    )
    .toBe(sessionId);

  await waitForSessionSetup(request, sessionId);
  await expect(page.getByTestId("play-prompt-input")).toBeEnabled();

  logSmokeStatus(`submitting create-game prompt in session ${sessionId}`);
  await page.getByTestId("play-prompt-input").fill(createGamePrompt);
  await page.getByTestId("play-prompt-send").click();

  await expect(page.getByTestId("play-job-state")).toHaveText("Streaming…", {
    timeout: 20_000,
  });

  const latestJobId = await waitForLatestJob(request, sessionId);

  logSmokeStatus(
    `waiting for dashboard to show job ${latestJobId} as completed`,
  );
  await expect
    .poll(
      async () =>
        (await page.getByTestId("play-job-state").textContent())?.trim(),
      {
        timeout: 120_000,
      },
    )
    .toBe("Completed");

  logSmokeStatus(`reading tool events for job ${latestJobId}`);
  const eventsResponse = await requireOk(
    request,
    `${orchestratorBaseUrl}/jobs/${latestJobId}/events`,
    `job events for ${latestJobId}`,
  );
  const eventsPayload = (await eventsResponse.json()) as JobEventsResponse;
  logSmokeChatTranscript(createGamePrompt, eventsPayload.events);
  const gameSessionId = extractCreatedGameSessionId(eventsPayload.events);
  if (!gameSessionId) {
    throw new Error(
      `Smoke run completed but did not emit a game-service_create_game tool result for job ${latestJobId}`,
    );
  }

  logSmokeStatus(`tool result created game session ${gameSessionId}`);
  await waitForCreatedGameState(request, gameSessionId);

  logSmokeStatus(`cleaning up game ${gameSessionId} and session ${sessionId}`);
  await request.delete(`${gameServiceBaseUrl}/games/${gameSessionId}`);
  await request.post(`${orchestratorBaseUrl}/sessions/${sessionId}/terminate`);
  logSmokeStatus("smoke run completed successfully");
});
