import {
  CardProviderResponse,
  ContextMetadata,
  DashboardConfig,
  GameSession,
  JobDetail,
  JobEventResponse,
  JobSummary,
  McpAssignmentResponse,
  McpRegistryResponse,
  PersonaRequest,
  PersonaResponse,
  PlayerConfigRequest,
  PlayerConfigResponse,
  ProviderResponse,
  SessionDetail,
  SessionJobsResponse,
  SessionMode,
  SessionSummary,
  SkillDefinitionResponse,
  JsonValue,
  UserQuestionAnswerRequest,
  UserQuestionResponse,
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
    default_subagent_persona?: string | null;
    session_mode?: SessionMode;
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
    default_subagent_persona?: string | null;
    session_mode?: SessionMode;
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

export async function listGlobalMcps(): Promise<McpRegistryResponse[]> {
  return (
    await getJson<{ mcps: McpRegistryResponse[] }>(
      "/api/proxy/orchestrator/mcps"
    )
  ).mcps;
}

export async function addMcpRegistry(body: {
  name: string;
  transport: string;
  server_url: string;
  headers?: Record<string, string>;
}): Promise<McpRegistryResponse> {
  return (
    await sendJson<{ mcp: McpRegistryResponse }>(
      "/api/proxy/orchestrator/mcps",
      "POST",
      body
    )
  ).mcp;
}

export async function removeMcpRegistry(mcpName: string) {
  await sendNoContent(`/api/proxy/orchestrator/mcps/${mcpName}`, "DELETE");
}

export async function enableMcpForSession(
  sessionId: string,
  mcpName: string,
  enabled: boolean
): Promise<McpAssignmentResponse> {
  return (
    await sendJson<{ mcp: McpAssignmentResponse }>(
      `/api/proxy/orchestrator/sessions/${sessionId}/mcps/${mcpName}`,
      "PATCH",
      { enabled }
    )
  ).mcp;
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

/**
 * Permanently remove a session and everything recorded under it. The
 * orchestrator cancels any in-flight job before deleting, so this also covers a
 * session that is still executing.
 */
export async function deleteSession(sessionId: string) {
  await sendNoContent(
    `/api/proxy/orchestrator/sessions/${sessionId}`,
    "DELETE"
  );
}

/**
 * Submit a prompt, naming the skills the message mentions.
 *
 * Only names travel: the orchestrator reads each skill's content from its own
 * skill roots and puts it in front of the prompt for that turn.
 */
export async function submitPrompt(
  sessionId: string,
  prompt: string,
  inlineSkills: string[] = []
): Promise<JobSummary> {
  return (
    await sendJson<{ job: JobSummary }>(
      `/api/proxy/orchestrator/sessions/${sessionId}/prompts`,
      "POST",
      { prompt, inline_skills: inlineSkills }
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

/**
 * Answer a question the model asked through `ask_user`.
 *
 * Rejects with the server's `detail` — notably the 409 raised once the question
 * is no longer pending (already answered, timed out, or the job reached a
 * terminal status) — so the caller can show it verbatim instead of retrying.
 */
export async function answerUserQuestion(
  jobId: string,
  questionId: string,
  body: UserQuestionAnswerRequest
): Promise<UserQuestionResponse> {
  return (
    await sendJson<{ question: UserQuestionResponse }>(
      `/api/proxy/orchestrator/jobs/${jobId}/questions/${questionId}/answer`,
      "POST",
      body
    )
  ).question;
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

interface SessionMetadata {
  session_id: string;
  plugin_name: string;
  plugin_id: number;
  room_slug: string;
  created_at: string;
}

export async function listGames(): Promise<GameSession[]> {
  const { sessions } = await getJson<{ sessions: SessionMetadata[] }>(
    "/api/proxy/game/games"
  );
  return sessions.map((s) => ({
    id: s.session_id,
    plugin: s.plugin_name,
    plugin_id: s.plugin_id,
    room_slug: s.room_slug,
    created_at: s.created_at,
  }));
}

// --- Per-seat player agents (orchestrated multi-player games) ---

export async function listPlayerAgents(
  sessionId: string
): Promise<PlayerConfigResponse[]> {
  return (
    await getJson<{ players: PlayerConfigResponse[] }>(
      `/api/proxy/orchestrator/sessions/${sessionId}/players`
    )
  ).players;
}

export async function setPlayerAgent(
  sessionId: string,
  playerId: string,
  body: PlayerConfigRequest
): Promise<PlayerConfigResponse> {
  return (
    await sendJson<{ player: PlayerConfigResponse }>(
      `/api/proxy/orchestrator/sessions/${sessionId}/players/${playerId}`,
      "PUT",
      body
    )
  ).player;
}

export async function deletePlayerAgent(
  sessionId: string,
  playerId: string
): Promise<void> {
  await sendNoContent(
    `/api/proxy/orchestrator/sessions/${sessionId}/players/${playerId}`,
    "DELETE"
  );
}

// --- Agent personas (reusable subagent configurations) ---

export async function listPersonas(): Promise<PersonaResponse[]> {
  return (
    await getJson<{ personas: PersonaResponse[] }>(
      "/api/proxy/orchestrator/personas"
    )
  ).personas;
}

export async function savePersona(
  name: string,
  body: PersonaRequest
): Promise<PersonaResponse> {
  return (
    await sendJson<{ persona: PersonaResponse }>(
      `/api/proxy/orchestrator/personas/${encodeURIComponent(name)}`,
      "PUT",
      body
    )
  ).persona;
}

export async function deletePersona(name: string): Promise<void> {
  await sendNoContent(
    `/api/proxy/orchestrator/personas/${encodeURIComponent(name)}`,
    "DELETE"
  );
}
