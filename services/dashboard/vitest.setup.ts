import "@testing-library/jest-dom/vitest";
import { beforeEach } from "vitest";

/**
 * Environment variables `features/config/lib/dashboard-config.ts` reads.
 *
 * The dashboard resolves service URLs and session defaults (provider, model,
 * skills, MCP wiring) from `process.env`. A developer who exports this stack's
 * configuration -- pointing the dashboard at the Docker hostnames, or defaulting
 * sessions to whichever provider they hold a key for -- would otherwise change
 * what these tests observe. Tests assert on behaviour, so they start from the
 * documented defaults and set explicitly whatever they actually care about.
 *
 * `features/config/__tests__/dashboard-config.test.ts` fails if this list drifts
 * out of sync with the variables the config module reads.
 */
export const DASHBOARD_CONFIG_ENV_VARS = [
  "AGENT_ORCHESTRATOR_URL",
  "GAME_SERVICE_URL",
  "HISTORY_SERVICE_URL",
  "EVAL_SERVICE_URL",
  "DRAGNCARDS_FRONTEND_URL",
  "MARVEL_LCG_BASE_URL",
  "BIFROST_UI_URL",
  "AGENT_ORCHESTRATOR_OPENAPI_PATH",
  "GAME_SERVICE_OPENAPI_PATH",
  "HISTORY_SERVICE_OPENAPI_PATH",
  "EVAL_SERVICE_OPENAPI_PATH",
  "APP_NAME",
  "DEFAULT_PROVIDER_ID",
  "DEFAULT_MODEL_NAME",
  "DEFAULT_GAME_SERVICE_MCP_ENABLED",
  "DEFAULT_GAME_SERVICE_MCP_NAME",
  "DEFAULT_GAME_SERVICE_MCP_TRANSPORT",
  "DEFAULT_GAME_SERVICE_MCP_URL",
  "GAME_SERVICE_MCP_URL",
  "DEFAULT_SKILLS",
  "DEFAULT_CUSTOM_MCPS_JSON",
  "DEFAULT_REASONING_ENABLED",
  "DEFAULT_REASONING_EFFORT",
] as const;

beforeEach(() => {
  for (const name of DASHBOARD_CONFIG_ENV_VARS) {
    delete process.env[name];
  }
});
