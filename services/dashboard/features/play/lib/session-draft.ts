import {
  CustomMcpDraft,
  DashboardConfig,
  GameSessionMetadata,
  JsonValue,
  ReasoningDraft,
  SessionDetail,
  SessionDraft,
} from "@/features/shared/lib/types";

function safeJsonStringify(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function isRecord(value: JsonValue | undefined): value is Record<string, JsonValue> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function buildDefaultReasoningDraft(): ReasoningDraft {
  return {
    enabled: false,
    effort: "medium",
    maxTokens: "",
  };
}

function extractReasoningDraft(options: Record<string, JsonValue>): ReasoningDraft {
  const raw = options.reasoning;
  if (!isRecord(raw)) {
    return buildDefaultReasoningDraft();
  }

  const effort = raw.effort;
  const maxTokens = raw.max_tokens;
  return {
    enabled: true,
    effort:
      effort === "low" || effort === "medium" || effort === "high"
        ? effort
        : "medium",
    maxTokens: typeof maxTokens === "number" && Number.isFinite(maxTokens) ? String(maxTokens) : "",
  };
}

export function applyReasoningToGatewayOptions(
  gatewayOptions: Record<string, JsonValue>,
  reasoning: ReasoningDraft,
): Record<string, JsonValue> {
  const nextOptions: Record<string, JsonValue> = { ...gatewayOptions };
  if (!reasoning.enabled) {
    delete nextOptions.reasoning;
    return nextOptions;
  }

  const reasoningOptions: Record<string, JsonValue> = {
    effort: reasoning.effort,
  };
  const maxTokens = reasoning.maxTokens.trim();
  if (maxTokens) {
    const parsed = Number(maxTokens);
    if (!Number.isInteger(parsed) || parsed <= 0) {
      throw new Error("Reasoning max tokens must be a positive integer");
    }
    reasoningOptions.max_tokens = parsed;
  }
  nextOptions.reasoning = reasoningOptions;
  return nextOptions;
}

export function createDefaultDraft(config: DashboardConfig): SessionDraft {
  const today = new Date().toLocaleString("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).replace(",", "");
  return {
    name: today,
    providerId: config.defaultProviderId,
    modelName: config.defaultModelName,
    reasoning: buildDefaultReasoningDraft(),
    gatewayOptionsText: safeJsonStringify({}),
    providerOptionsText: safeJsonStringify({}),
    selectedSkills: config.defaultSkills,
    createGameSession: true,
    gamePluginName: config.defaultGamePlugin,
    enableDefaultGameServiceMcp: config.defaultGameServiceMcpEnabled,
    customMcpsText: safeJsonStringify(config.defaultCustomMcps),
  };
}

export function buildDraftFromSession(
  config: DashboardConfig,
  session: SessionDetail,
): SessionDraft {
  const defaultDraft = createDefaultDraft(config);
  const customMcps = session.mcps.filter(
    (mcp) =>
      !(
        mcp.name === config.defaultGameServiceMcpName &&
        mcp.server_url === config.defaultGameServiceMcpUrl
      ),
  );

  return {
    ...defaultDraft,
    name: session.name ?? "",
    providerId: session.model_config?.provider_id ?? defaultDraft.providerId,
    modelName: session.model_config?.model_name ?? defaultDraft.modelName,
    reasoning: extractReasoningDraft(session.model_config?.gateway_options ?? {}),
    gatewayOptionsText: safeJsonStringify(session.model_config?.gateway_options ?? {}),
    providerOptionsText: safeJsonStringify(session.model_config?.provider_options ?? {}),
    selectedSkills: session.skills.map((skill) => skill.skill_name),
    enableDefaultGameServiceMcp: session.mcps.some(
      (mcp) =>
        mcp.name === config.defaultGameServiceMcpName &&
        mcp.server_url === config.defaultGameServiceMcpUrl,
    ),
    customMcpsText: safeJsonStringify(
      customMcps.map((mcp) => ({
        name: mcp.name,
        transport: mcp.transport,
        server_url: mcp.server_url,
        headers: mcp.headers as Record<string, string>,
      })),
    ),
    gamePluginName: extractGameSession(session.metadata)?.plugin_name ?? defaultDraft.gamePluginName,
    createGameSession: Boolean(extractGameSession(session.metadata)),
  };
}

export function parseJsonObject(text: string, label: string): Record<string, JsonValue> {
  try {
    const parsed = JSON.parse(text) as unknown;
    if (!isRecord(parsed as JsonValue)) {
      throw new Error(`${label} must be a JSON object`);
    }
    return parsed as Record<string, JsonValue>;
  } catch (error) {
    if (error instanceof Error && error.message.includes(label)) {
      throw error;
    }
    throw new Error(`${label} must be valid JSON`);
  }
}

export function parseCustomMcps(text: string): CustomMcpDraft[] {
  try {
    const parsed = JSON.parse(text) as unknown;
    if (!Array.isArray(parsed)) {
      throw new Error("Custom MCPs must be a JSON array");
    }
    return parsed as CustomMcpDraft[];
  } catch (error) {
    if (error instanceof Error && error.message.includes("Custom MCPs")) {
      throw error;
    }
    throw new Error("Custom MCPs must be valid JSON");
  }
}

export function extractGameSession(
  metadata: Record<string, JsonValue>,
): GameSessionMetadata | null {
  const raw = metadata.game_session;
  if (!isRecord(raw)) {
    return null;
  }

  if (
    typeof raw.session_id !== "string" ||
    typeof raw.plugin_name !== "string" ||
    typeof raw.plugin_id !== "number" ||
    typeof raw.room_slug !== "string" ||
    typeof raw.created_at !== "string"
  ) {
    return null;
  }

  return {
    session_id: raw.session_id,
    plugin_name: raw.plugin_name,
    plugin_id: raw.plugin_id,
    room_slug: raw.room_slug,
    created_at: raw.created_at,
    frontend_url:
      typeof raw.frontend_url === "string" ? raw.frontend_url : null,
  };
}

export function buildDragnCardsRoomUrl(
  dragncardsFrontendUrl: string,
  metadata: Record<string, JsonValue>,
): string | null {
  const gameSession = extractGameSession(metadata);
  if (!gameSession) {
    return null;
  }
  if (gameSession.frontend_url) {
    return gameSession.frontend_url;
  }

  const baseUrl = dragncardsFrontendUrl.replace(/\/$/, "");
  return `${baseUrl}/room/${gameSession.room_slug}`;
}
