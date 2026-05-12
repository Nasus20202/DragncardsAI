import {
  CardProviderResponse,
  ContextMetadata,
  DashboardConfig,
  JobDetail,
  JobEventResponse,
  JobSummary,
  JsonValue,
  McpAssignmentResponse,
  ProviderResponse,
  SessionDetail,
  SessionJobsResponse,
  SessionSummary,
  SkillDefinitionResponse,
} from "@/features/shared/lib/types";

interface DashboardConfigResponse {
  config: DashboardConfig;
}

type JsonHeaders = { "content-type": "application/json" };

async function request(path: string, init?: RequestInit): Promise<Response> {
  return fetch(path, init);
}

async function getJson<T>(path: string): Promise<T> {
  const response = await request(path, { cache: "no-store" });
  return readJson<T>(response);
}

async function sendJson<T>(
  path: string,
  method: "POST" | "PATCH" | "PUT",
  body?: unknown
): Promise<T> {
  const headers: JsonHeaders = { "content-type": "application/json" };
  const response = await request(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return readJson<T>(response);
}

async function sendNoContent(path: string, method: "DELETE" | "POST") {
  const response = await request(path, { method });
  if (!response.ok && response.status !== 204) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(
      body?.detail ?? `${response.status} ${response.statusText}`
    );
  }
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(
      body?.detail ?? `${response.status} ${response.statusText}`
    );
  }

  return (await response.json()) as T;
}

export async function fetchDashboardConfig(): Promise<DashboardConfig> {
  const payload = await getJson<DashboardConfigResponse>("/api/config");
  return payload.config;
}

export async function listProviders(): Promise<ProviderResponse[]> {
  return (
    await getJson<{ providers: ProviderResponse[] }>(
      "/api/proxy/orchestrator/providers"
    )
  ).providers;
}

export async function listGamePlugins(): Promise<CardProviderResponse[]> {
  return (
    await getJson<{ providers: CardProviderResponse[] }>(
      "/api/proxy/game/card-providers"
    )
  ).providers;
}

export async function listAvailableSkills(): Promise<
  SkillDefinitionResponse[]
> {
  return (
    await getJson<{ skills: SkillDefinitionResponse[] }>(
      "/api/proxy/orchestrator/skills"
    )
  ).skills;
}

export async function listSessions(): Promise<SessionSummary[]> {
  return (
    await getJson<{ sessions: SessionSummary[] }>(
      "/api/proxy/orchestrator/sessions"
    )
  ).sessions;
}

export async function getSession(sessionId: string): Promise<SessionDetail> {
  return (
    await getJson<{ session: SessionDetail }>(
      `/api/proxy/orchestrator/sessions/${sessionId}`
    )
  ).session;
}

export async function listSessionJobs(
  sessionId: string
): Promise<SessionJobsResponse> {
  return getJson<SessionJobsResponse>(
    `/api/proxy/orchestrator/sessions/${sessionId}/jobs`
  );
}

export async function createSession(
  name: string,
  body?: {
    context_recent_message_limit?: number | null;
    context_recent_tool_exchange_limit?: number | null;
  }
): Promise<SessionDetail> {
  return (
    await sendJson<{ session: SessionDetail }>(
      "/api/proxy/orchestrator/sessions",
      "POST",
      { name, metadata: {}, ...(body ?? {}) }
    )
  ).session;
}

export async function updateSession(
  sessionId: string,
  body: {
    name?: string | null;
    metadata?: Record<string, JsonValue>;
    context_recent_message_limit?: number | null;
    context_recent_tool_exchange_limit?: number | null;
  }
): Promise<SessionDetail> {
  return (
    await sendJson<{ session: SessionDetail }>(
      `/api/proxy/orchestrator/sessions/${sessionId}`,
      "PATCH",
      body
    )
  ).session;
}

export async function setModelConfig(
  sessionId: string,
  body: {
    provider_id: string;
    model_name: string;
    gateway_options: Record<string, JsonValue>;
    provider_options: Record<string, JsonValue>;
  }
) {
  return sendJson<{ model_config: unknown }>(
    `/api/proxy/orchestrator/sessions/${sessionId}/model-config`,
    "PUT",
    body
  );
}

export async function addSkill(sessionId: string, skillName: string) {
  return sendJson<{ skill: unknown }>(
    `/api/proxy/orchestrator/sessions/${sessionId}/skills`,
    "POST",
    { skill_name: skillName }
  );
}

export async function removeSkill(sessionId: string, skillName: string) {
  await sendNoContent(
    `/api/proxy/orchestrator/sessions/${sessionId}/skills/${skillName}`,
    "DELETE"
  );
}

export async function listSessionMcps(
  sessionId: string
): Promise<McpAssignmentResponse[]> {
  return (
    await getJson<{ mcps: McpAssignmentResponse[] }>(
      `/api/proxy/orchestrator/sessions/${sessionId}/mcps`
    )
  ).mcps;
}

export async function addMcp(
  sessionId: string,
  body: {
    name: string;
    transport: string;
    server_url: string;
    headers?: Record<string, string>;
  }
) {
  return sendJson<{ mcp: McpAssignmentResponse }>(
    `/api/proxy/orchestrator/sessions/${sessionId}/mcps`,
    "POST",
    body
  );
}

export async function removeMcp(sessionId: string, assignmentName: string) {
  await sendNoContent(
    `/api/proxy/orchestrator/sessions/${sessionId}/mcps/${assignmentName}`,
    "DELETE"
  );
}

export async function terminateSession(
  sessionId: string
): Promise<SessionDetail> {
  return (
    await sendJson<{ session: SessionDetail }>(
      `/api/proxy/orchestrator/sessions/${sessionId}/terminate`,
      "POST"
    )
  ).session;
}

export async function submitPrompt(
  sessionId: string,
  prompt: string
): Promise<JobSummary> {
  return (
    await sendJson<{ job: JobSummary }>(
      `/api/proxy/orchestrator/sessions/${sessionId}/prompts`,
      "POST",
      { prompt }
    )
  ).job;
}

export async function getJob(jobId: string): Promise<JobDetail> {
  return (
    await getJson<{ job: JobDetail }>(`/api/proxy/orchestrator/jobs/${jobId}`)
  ).job;
}

export async function cancelJob(jobId: string): Promise<JobSummary> {
  return (
    await sendJson<{ job: JobSummary }>(
      `/api/proxy/orchestrator/jobs/${jobId}/cancel`,
      "POST"
    )
  ).job;
}

export async function getJobEvents(jobId: string): Promise<JobEventResponse[]> {
  return (
    await getJson<{ events: JobEventResponse[] }>(
      `/api/proxy/orchestrator/jobs/${jobId}/events`
    )
  ).events;
}

export async function getContextMetadata(
  sessionId: string
): Promise<ContextMetadata> {
  return getJson<ContextMetadata>(
    `/api/proxy/orchestrator/sessions/${sessionId}/context`
  );
}

export async function compactSession(
  sessionId: string
): Promise<ContextMetadata> {
  return sendJson<ContextMetadata>(
    `/api/proxy/orchestrator/sessions/${sessionId}/compact`,
    "POST"
  );
}
