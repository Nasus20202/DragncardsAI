import { DashboardConfig, CustomMcpDraft } from "@/features/shared/lib/types";

const DEFAULT_APP_NAME = "DragnCardsAI Dashboard";

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

export function getServerConfig() {
  const orchestratorUrl = process.env.AGENT_ORCHESTRATOR_URL ?? "http://localhost:8010";
  const gameServiceUrl = process.env.GAME_SERVICE_URL ?? "http://localhost:8000";
  const dragncardsFrontendUrl = process.env.DRAGNCARDS_FRONTEND_URL ?? "http://localhost:3000";
  const isLocalDevelopment =
    orchestratorUrl.includes("localhost") || orchestratorUrl.includes("127.0.0.1");

  return {
    orchestratorUrl,
    gameServiceUrl,
    dragncardsFrontendUrl,
    orchestratorOpenApiPath:
      process.env.AGENT_ORCHESTRATOR_OPENAPI_PATH ?? "/openapi.json",
    gameServiceOpenApiPath: process.env.GAME_SERVICE_OPENAPI_PATH ?? "/openapi.json",
    publicConfig: {
      appName: process.env.DASHBOARD_APP_NAME ?? DEFAULT_APP_NAME,
      dragncardsFrontendUrl,
      defaultProviderId: process.env.DASHBOARD_DEFAULT_PROVIDER_ID ?? "openai",
      defaultModelName: process.env.DASHBOARD_DEFAULT_MODEL_NAME ?? "gpt-4o-mini",
      defaultGamePlugin:
        process.env.DASHBOARD_DEFAULT_GAME_PLUGIN ?? "marvel-champions",
      defaultGameServiceMcpEnabled: parseBoolean(
        process.env.DASHBOARD_DEFAULT_GAME_SERVICE_MCP_ENABLED,
        true,
      ),
      defaultGameServiceMcpName:
        process.env.DASHBOARD_DEFAULT_GAME_SERVICE_MCP_NAME ?? "game-service",
      defaultGameServiceMcpTransport:
        process.env.DASHBOARD_DEFAULT_GAME_SERVICE_MCP_TRANSPORT ?? "streamable-http",
      defaultGameServiceMcpUrl:
        process.env.DASHBOARD_DEFAULT_GAME_SERVICE_MCP_URL ??
        (isLocalDevelopment ? "http://localhost:8000/mcp/" : "http://game-service:8000/mcp/"),
      defaultSkills: splitCsv(process.env.DASHBOARD_DEFAULT_SKILLS),
      defaultCustomMcps: parseCustomMcps(
        process.env.DASHBOARD_DEFAULT_CUSTOM_MCPS_JSON,
      ),
    } satisfies DashboardConfig,
  };
}

export function getPublicConfig(): DashboardConfig {
  return getServerConfig().publicConfig;
}
