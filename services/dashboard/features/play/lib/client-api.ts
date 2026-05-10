import {
  CardProviderResponse,
  DashboardConfig,
  GameSessionMetadata,
  JobDetail,
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

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `${response.status} ${response.statusText}`);
  }

  return (await response.json()) as T;
}

export async function fetchDashboardConfig(): Promise<DashboardConfig> {
  const response = await fetch("/api/config", { cache: "no-store" });
  const payload = await readJson<DashboardConfigResponse>(response);
  return payload.config;
}

export async function listProviders(): Promise<ProviderResponse[]> {
  const response = await fetch("/api/proxy/orchestrator/providers", { cache: "no-store" });
  return (await readJson<{ providers: ProviderResponse[] }>(response)).providers;
}

export async function listGamePlugins(): Promise<CardProviderResponse[]> {
  const response = await fetch("/api/proxy/game/card-providers", { cache: "no-store" });
  return (await readJson<{ providers: CardProviderResponse[] }>(response)).providers;
}

export async function listAvailableSkills(): Promise<SkillDefinitionResponse[]> {
  const response = await fetch("/api/proxy/orchestrator/skills", { cache: "no-store" });
  return (await readJson<{ skills: SkillDefinitionResponse[] }>(response)).skills;
}

export async function listSessions(): Promise<SessionSummary[]> {
  const response = await fetch("/api/proxy/orchestrator/sessions", { cache: "no-store" });
  return (await readJson<{ sessions: SessionSummary[] }>(response)).sessions;
}

export async function getSession(sessionId: string): Promise<SessionDetail> {
  const response = await fetch(`/api/proxy/orchestrator/sessions/${sessionId}`, {
    cache: "no-store",
  });
  return (await readJson<{ session: SessionDetail }>(response)).session;
}

export async function listSessionJobs(sessionId: string): Promise<SessionJobsResponse> {
  const response = await fetch(`/api/proxy/orchestrator/sessions/${sessionId}/jobs`, {
    cache: "no-store",
  });
  return readJson<SessionJobsResponse>(response);
}

export async function createSession(name: string): Promise<SessionDetail> {
  const response = await fetch("/api/proxy/orchestrator/sessions", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ name, metadata: {} }),
  });

  return (await readJson<{ session: SessionDetail }>(response)).session;
}

export async function updateSession(
  sessionId: string,
  body: { name?: string; metadata?: Record<string, JsonValue> },
): Promise<SessionDetail> {
  const response = await fetch(`/api/proxy/orchestrator/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });

  return (await readJson<{ session: SessionDetail }>(response)).session;
}

export async function setModelConfig(
  sessionId: string,
  body: {
    provider_id: string;
    model_name: string;
    gateway_options: Record<string, JsonValue>;
    provider_options: Record<string, JsonValue>;
  },
) {
  const response = await fetch(`/api/proxy/orchestrator/sessions/${sessionId}/model-config`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<{ model_config: unknown }>(response);
}

export async function addSkill(sessionId: string, skillName: string) {
  const response = await fetch(`/api/proxy/orchestrator/sessions/${sessionId}/skills`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ skill_name: skillName }),
  });
  return readJson<{ skill: unknown }>(response);
}

export async function removeSkill(sessionId: string, skillName: string) {
  const response = await fetch(`/api/proxy/orchestrator/sessions/${sessionId}/skills/${skillName}`, {
    method: "DELETE",
  });
  if (!response.ok && response.status !== 204) {
    throw new Error(`Failed to remove skill ${skillName}`);
  }
}

export async function listSessionMcps(sessionId: string): Promise<McpAssignmentResponse[]> {
  const response = await fetch(`/api/proxy/orchestrator/sessions/${sessionId}/mcps`, {
    cache: "no-store",
  });
  return (await readJson<{ mcps: McpAssignmentResponse[] }>(response)).mcps;
}

export async function addMcp(
  sessionId: string,
  body: { name: string; transport: string; server_url: string; headers?: Record<string, string> },
) {
  const response = await fetch(`/api/proxy/orchestrator/sessions/${sessionId}/mcps`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<{ mcp: McpAssignmentResponse }>(response);
}

export async function removeMcp(sessionId: string, assignmentName: string) {
  const response = await fetch(`/api/proxy/orchestrator/sessions/${sessionId}/mcps/${assignmentName}`, {
    method: "DELETE",
  });
  if (!response.ok && response.status !== 204) {
    throw new Error(`Failed to remove MCP ${assignmentName}`);
  }
}

export async function terminateSession(sessionId: string): Promise<SessionDetail> {
  const response = await fetch(`/api/proxy/orchestrator/sessions/${sessionId}/terminate`, {
    method: "POST",
  });
  return (await readJson<{ session: SessionDetail }>(response)).session;
}

export async function submitPrompt(sessionId: string, prompt: string): Promise<JobSummary> {
  const response = await fetch(`/api/proxy/orchestrator/sessions/${sessionId}/prompts`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  return (await readJson<{ job: JobSummary }>(response)).job;
}

export async function getJob(jobId: string): Promise<JobDetail> {
  const response = await fetch(`/api/proxy/orchestrator/jobs/${jobId}`, { cache: "no-store" });
  return (await readJson<{ job: JobDetail }>(response)).job;
}

export async function createGameSession(pluginName: string): Promise<GameSessionMetadata> {
  const response = await fetch("/api/proxy/game/games", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ plugin_name: pluginName }),
  });
  return (await readJson<{ session: GameSessionMetadata }>(response)).session;
}
