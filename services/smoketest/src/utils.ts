import { APIRequestContext, expect } from "@playwright/test";

import {
  gameServiceBaseUrl,
  llamaCppBaseUrl,
  orchestratorBaseUrl,
  smokeModelName,
  smokeModelProviderId,
} from "./config";
import type {
  JobEventsResponse,
  SessionDetailResponse,
  SessionJobsResponse,
  SessionListResponse,
  SessionToolsResponse,
} from "./types";

export function logSmokeStatus(message: string) {
  console.log(`[smoketest] ${message}`);
}

function stringifyPayload(value: unknown) {
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function readToolResultText(payload: Record<string, unknown>) {
  const result = payload.result;
  if (!result || typeof result !== "object") {
    return null;
  }

  const content = (result as { content?: unknown }).content;
  if (!Array.isArray(content)) {
    return null;
  }

  const firstText = content.find(
    (item) =>
      item &&
      typeof item === "object" &&
      typeof (item as { text?: unknown }).text === "string",
  ) as { text: string } | undefined;

  return firstText?.text ?? null;
}

export function logSmokeChatTranscript(
  prompt: string,
  events: JobEventsResponse["events"],
) {
  console.log("[smoketest][chat] user>");
  console.log(prompt);

  for (const event of events) {
    const payload = event.payload as Record<string, unknown>;

    switch (event.event_type) {
      case "reasoning": {
        if (typeof payload.text === "string" && payload.text.trim()) {
          console.log("[smoketest][chat] reasoning>");
          console.log(payload.text);
        }
        break;
      }
      case "model_output":
      case "completion": {
        if (typeof payload.text === "string" && payload.text.trim()) {
          console.log("[smoketest][chat] assistant>");
          console.log(payload.text);
        }
        break;
      }
      case "tool_call": {
        const toolName =
          typeof payload.exposed_tool_name === "string"
            ? payload.exposed_tool_name
            : typeof payload.tool_name === "string"
              ? payload.tool_name
              : "unknown_tool";
        console.log(`[smoketest][chat] tool_call ${toolName}>`);
        console.log(stringifyPayload(payload.arguments ?? payload));
        break;
      }
      case "tool_result": {
        const toolName =
          typeof payload.exposed_tool_name === "string"
            ? payload.exposed_tool_name
            : typeof payload.tool_name === "string"
              ? payload.tool_name
              : "unknown_tool";
        console.log(`[smoketest][chat] tool_result ${toolName}>`);
        console.log(
          readToolResultText(payload) ??
            stringifyPayload(payload.result ?? payload),
        );
        break;
      }
      case "failure": {
        console.log("[smoketest][chat] failure>");
        console.log(
          typeof payload.message === "string"
            ? payload.message
            : stringifyPayload(payload),
        );
        break;
      }
      case "cancellation": {
        console.log("[smoketest][chat] cancellation>");
        console.log(stringifyPayload(payload));
        break;
      }
      default:
        break;
    }
  }
}

export async function requireOk(
  request: APIRequestContext,
  url: string,
  label: string,
) {
  const response = await request.get(url);
  if (!response.ok()) {
    throw new Error(
      `Smoke dependency unavailable: ${label} at ${url} returned ${response.status()} ${response.statusText()}`,
    );
  }
  return response;
}

export async function requireSmokeEnvironment(request: APIRequestContext) {
  logSmokeStatus("checking smoke dependencies");
  const modelResponse = await requireOk(
    request,
    `${llamaCppBaseUrl.replace(/\/$/, "")}/models`,
    "llama.cpp smoke model",
  );
  const modelPayload = (await modelResponse.json()) as {
    data?: Array<{ id?: string }>;
  };
  const modelIds = (modelPayload.data ?? []).flatMap((item) =>
    typeof item.id === "string" ? [item.id] : [],
  );
  if (!modelIds.includes(smokeModelName)) {
    throw new Error(
      `Smoke dependency unavailable: llama.cpp endpoint does not advertise model ${smokeModelName}. Available models: ${modelIds.join(", ") || "none"}`,
    );
  }

  await requireOk(
    request,
    `${orchestratorBaseUrl}/health`,
    "agent-orchestrator",
  );
  await requireOk(request, `${gameServiceBaseUrl}/health`, "game-service");
  logSmokeStatus("smoke dependencies are reachable");
}

export async function waitForSessionSetup(
  request: APIRequestContext,
  sessionId: string,
) {
  logSmokeStatus(`waiting for session ${sessionId} model and MCP setup`);
  await expect
    .poll(
      async () => {
        const response = await requireOk(
          request,
          `${orchestratorBaseUrl}/sessions/${sessionId}`,
          `orchestrator session ${sessionId}`,
        );
        const payload = (await response.json()) as SessionDetailResponse;
        return {
          providerId: payload.session.model_config?.provider_id ?? null,
          modelName: payload.session.model_config?.model_name ?? null,
          mcps: payload.session.mcps.map((mcp) => mcp.name),
        };
      },
      { timeout: 15_000 },
    )
    .toEqual({
      providerId: smokeModelProviderId,
      modelName: `${smokeModelProviderId}/${smokeModelName}`,
      mcps: ["game-service"],
    });

  await expect
    .poll(
      async () => {
        const response = await requireOk(
          request,
          `${orchestratorBaseUrl}/sessions/${sessionId}/tools`,
          `tool catalog for session ${sessionId}`,
        );
        const payload = (await response.json()) as SessionToolsResponse;
        return payload.tools.some(
          (tool) => tool.name === "game-service_create_game",
        );
      },
      { timeout: 15_000 },
    )
    .toBe(true);

  logSmokeStatus(`session ${sessionId} is ready for prompt submission`);
}

export async function waitForCreatedSessionId(
  request: APIRequestContext,
  existingSessionIds: Set<string>,
) {
  let createdSessionId = "";
  let attempts = 0;

  await expect
    .poll(
      async () => {
        attempts += 1;
        const response = await requireOk(
          request,
          `${orchestratorBaseUrl}/sessions`,
          "orchestrator sessions",
        );
        const payload = (await response.json()) as SessionListResponse;
        const createdSession = [...payload.sessions]
          .filter((session) => !existingSessionIds.has(session.id))
          .sort((left, right) =>
            left.created_at.localeCompare(right.created_at),
          )
          .at(-1);
        createdSessionId = createdSession?.id ?? "";
        if (!createdSessionId && (attempts === 1 || attempts % 5 === 0)) {
          logSmokeStatus("waiting for dashboard to create a new session");
        }
        return createdSessionId;
      },
      { timeout: 15_000 },
    )
    .not.toBe("");

  logSmokeStatus(`created session ${createdSessionId}`);
  return createdSessionId;
}

export async function waitForLatestJob(
  request: APIRequestContext,
  sessionId: string,
) {
  let latestJobId = "";
  let lastStatus: string | null = null;

  logSmokeStatus(`waiting for latest job in session ${sessionId} to complete`);
  await expect
    .poll(
      async () => {
        const response = await requireOk(
          request,
          `${orchestratorBaseUrl}/sessions/${sessionId}/jobs`,
          `jobs for session ${sessionId}`,
        );
        const payload = (await response.json()) as SessionJobsResponse;
        const latestJob = [...payload.jobs]
          .sort((left, right) =>
            left.created_at.localeCompare(right.created_at),
          )
          .at(-1);
        latestJobId = latestJob?.id ?? "";
        const status = latestJob?.status ?? null;
        if (status !== lastStatus) {
          if (latestJobId) {
            logSmokeStatus(`job ${latestJobId} status: ${status ?? "pending"}`);
          } else {
            logSmokeStatus("waiting for the first prompt job to appear");
          }
          lastStatus = status;
        }
        return status;
      },
      { timeout: 120_000 },
    )
    .toBe("completed");

  if (!latestJobId) {
    throw new Error(`Smoke run did not create a job for session ${sessionId}`);
  }

  logSmokeStatus(`job ${latestJobId} completed`);
  return latestJobId;
}

export function extractCreatedGameSessionId(
  events: JobEventsResponse["events"],
) {
  for (const event of events) {
    if (event.event_type !== "tool_result") {
      continue;
    }
    if (event.payload.exposed_tool_name !== "game-service_create_game") {
      continue;
    }
    const result = event.payload.result as
      { content?: Array<{ text?: string }> } | undefined;
    const rawText = result?.content?.[0]?.text;
    if (typeof rawText !== "string") {
      continue;
    }
    const parsed = JSON.parse(rawText) as {
      session?: { session_id?: string };
    };
    const sessionId = parsed.session?.session_id;
    if (typeof sessionId === "string" && sessionId.length > 0) {
      return sessionId;
    }
  }
  return null;
}

export async function waitForCreatedGameState(
  request: APIRequestContext,
  gameSessionId: string,
) {
  let attempts = 0;

  logSmokeStatus(`waiting for game ${gameSessionId} state to become available`);
  await expect
    .poll(
      async () => {
        attempts += 1;
        const response = await request.get(
          `${gameServiceBaseUrl}/games/${gameSessionId}/state/raw`,
        );
        if (!response.ok()) {
          if (attempts === 1 || attempts % 5 === 0) {
            logSmokeStatus(
              `game ${gameSessionId} state not ready yet (${response.status()})`,
            );
          }
          return null;
        }
        const payload = (await response.json()) as {
          game?: unknown;
        };
        if (!payload.game && (attempts === 1 || attempts % 5 === 0)) {
          logSmokeStatus(
            `game ${gameSessionId} exists but state is still empty`,
          );
        }
        return payload.game ? "ready" : null;
      },
      { timeout: 30_000, intervals: [500, 1000, 2000] },
    )
    .toBe("ready");

  logSmokeStatus(`game ${gameSessionId} state is ready`);
}
