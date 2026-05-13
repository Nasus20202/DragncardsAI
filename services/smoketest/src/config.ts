import process from "process";

export const smokeModelProviderId =
  process.env.SMOKE_MODEL_PROVIDER_ID ?? "lmstudio";
export const smokeModelName = process.env.SMOKE_MODEL_NAME ?? "qwen3.5-0.8b";
export const orchestratorBaseUrl =
  process.env.AGENT_ORCHESTRATOR_SMOKE_URL ?? "http://127.0.0.1:4002";
export const gameServiceBaseUrl =
  process.env.GAME_SERVICE_SMOKE_URL ?? "http://127.0.0.1:4001";
export const llamaCppBaseUrl =
  process.env.LLAMA_CPP_SMOKE_URL ?? "http://127.0.0.1:1234/v1";

export const createGamePrompt =
  'Create one new Marvel Champions game using the game-service create_game tool. Use plugin_name "marvel-champions". After the game is created, stop and report the created session_id.';
