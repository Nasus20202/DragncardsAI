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

export function getServerConfig() {
  const orchestratorUrl =
    process.env.AGENT_ORCHESTRATOR_URL ?? "http://localhost:4002";
  const gameServiceUrl =
    process.env.GAME_SERVICE_URL ?? "http://localhost:4001";
  const isLocalDevelopment =
    orchestratorUrl.includes("localhost") ||
    orchestratorUrl.includes("127.0.0.1");
  const dragncardsFrontendUrl =
    process.env.DRAGNCARDS_FRONTEND_URL ?? "http://localhost:3000";

  return {
    orchestratorUrl,
    gameServiceUrl,
    dragncardsFrontendUrl,
    orchestratorOpenApiPath:
      process.env.AGENT_ORCHESTRATOR_OPENAPI_PATH ?? "/openapi.json",
    gameServiceOpenApiPath:
      process.env.GAME_SERVICE_OPENAPI_PATH ?? "/openapi.json",
    publicConfig: {
      appName: process.env.APP_NAME ?? DEFAULT_APP_NAME,
      defaultProviderId: process.env.DEFAULT_PROVIDER_ID ?? "openai",
      defaultModelName: process.env.DEFAULT_MODEL_NAME ?? "gpt-4o-mini",
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
    } satisfies DashboardConfig,
  };
}

export function getPublicConfig(): DashboardConfig {
  return getServerConfig().publicConfig;
}
