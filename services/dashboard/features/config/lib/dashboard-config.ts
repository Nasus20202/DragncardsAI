import { DashboardConfig, CustomMcpDraft } from "@/features/shared/lib/types";

const DEFAULT_APP_NAME = "DragncardsAI";

function splitCsv(raw: string | undefined): string[] {
  if (!raw) {
    return [];
  }

  return raw
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseBoolean(raw: string | undefined, fallback: boolean): boolean {
  if (!raw) {
    return fallback;
  }

  return ["1", "true", "yes", "on"].includes(raw.toLowerCase());
}

function parseCustomMcps(raw: string | undefined): CustomMcpDraft[] {
  if (!raw) {
    return [];
  }

  try {
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as CustomMcpDraft[]) : [];
  } catch {
    return [];
  }
}

function parseReasoningEffort(
  raw: string | undefined
): "low" | "medium" | "high" {
  if (raw === "low" || raw === "high") return raw;
  return "medium";
}

export function getServerConfig() {
  const orchestratorUrl =
    process.env.AGENT_ORCHESTRATOR_URL ?? "http://localhost:4002";
  const gameServiceUrl =
    process.env.GAME_SERVICE_URL ?? "http://localhost:4001";
  const historyServiceUrl =
    process.env.HISTORY_SERVICE_URL ?? "http://localhost:4004";
  const evalServiceUrl =
    process.env.EVAL_SERVICE_URL ?? "http://localhost:4005";
  const isLocalDevelopment =
    orchestratorUrl.includes("localhost") ||
    orchestratorUrl.includes("127.0.0.1");
  const dragncardsFrontendUrl =
    process.env.DRAGNCARDS_FRONTEND_URL ?? "http://localhost:3000";
  // Browser-reachable Bifrost UI. Deliberately distinct from the services'
  // BIFROST_URL, which is the Docker-internal gateway address.
  const bifrostUiUrl = process.env.BIFROST_UI_URL ?? "http://localhost:4003";

  return {
    orchestratorUrl,
    gameServiceUrl,
    historyServiceUrl,
    evalServiceUrl,
    dragncardsFrontendUrl,
    bifrostUiUrl,
    orchestratorOpenApiPath:
      process.env.AGENT_ORCHESTRATOR_OPENAPI_PATH ?? "/openapi.json",
    gameServiceOpenApiPath:
      process.env.GAME_SERVICE_OPENAPI_PATH ?? "/openapi.json",
    publicConfig: {
      appName: process.env.APP_NAME ?? DEFAULT_APP_NAME,
      defaultProviderId: process.env.DEFAULT_PROVIDER_ID ?? "openrouter",
      defaultModelName:
        process.env.DEFAULT_MODEL_NAME ?? "openrouter/openrouter/free",
      defaultGameServiceMcpEnabled: parseBoolean(
        process.env.DEFAULT_GAME_SERVICE_MCP_ENABLED,
        true
      ),
      defaultGameServiceMcpName:
        process.env.DEFAULT_GAME_SERVICE_MCP_NAME ?? "game-service",
      defaultGameServiceMcpTransport:
        process.env.DEFAULT_GAME_SERVICE_MCP_TRANSPORT ?? "streamable-http",
      defaultGameServiceMcpUrl:
        process.env.DEFAULT_GAME_SERVICE_MCP_URL ??
        process.env.GAME_SERVICE_MCP_URL ??
        (isLocalDevelopment
          ? "http://localhost:4001/mcp/"
          : "http://game-service:8000/mcp/"),
      defaultSkills: splitCsv(process.env.DEFAULT_SKILLS),
      defaultCustomMcps: parseCustomMcps(process.env.DEFAULT_CUSTOM_MCPS_JSON),
      dragncardsFrontendUrl,
      bifrostUiUrl,
      defaultReasoningEnabled: parseBoolean(
        process.env.DEFAULT_REASONING_ENABLED,
        true
      ),
      defaultReasoningEffort: parseReasoningEffort(
        process.env.DEFAULT_REASONING_EFFORT
      ),
    } satisfies DashboardConfig,
  };
}

export function getPublicConfig(): DashboardConfig {
  return getServerConfig().publicConfig;
}
