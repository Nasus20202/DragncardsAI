export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

export interface PageInfo {
  limit: number;
  offset: number;
  total: number;
}

export interface ProviderResponse {
  provider_id: string;
  model_prefix: string;
  models: string[];
  available: boolean;
  error: string | null;
}

export interface CardProviderResponse {
  provider: string;
  display_name: string;
  default: boolean;
  filters: Array<Record<string, JsonValue>>;
  load_groups: string[];
}

export interface SkillDefinitionResponse {
  name: string;
  path: string;
  content_markdown: string;
}

export interface ModelConfigResponse {
  provider_id: string;
  model_name: string;
  gateway_options: Record<string, JsonValue>;
  provider_options: Record<string, JsonValue>;
  updated_at: string;
}

export interface SkillAssignmentResponse {
  id: string;
  skill_name: string;
  skill_path: string;
  created_at: string;
}

export interface McpAssignmentResponse {
  id: string;
  name: string;
  transport: string;
  server_url: string;
  headers: Record<string, JsonValue>;
  created_at: string;
  updated_at: string;
}

export interface JobSummary {
  id: string;
  prompt_run_id: string;
  status: string;
  attempts: number;
  max_attempts: number;
  error_code: string | null;
  error_message: string | null;
  result_text: string | null;
  cancellation_requested_at: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  latest_event_id: string | null;
  latest_event_type: string | null;
}

export interface PromptRunSummary {
  id: string;
  prompt: string;
  status: string;
  metadata: Record<string, JsonValue>;
  created_at: string;
  updated_at: string;
}

export interface JobEventResponse {
  id: string;
  event_type: string;
  payload: Record<string, JsonValue>;
  created_at: string;
}

export interface SessionToolResponse {
  name: string;
  assignment_name: string;
  transport: string;
  server_url: string;
  actual_name: string;
  description: string | null;
  parameters: Record<string, JsonValue>;
}

export interface SessionSummary {
  id: string;
  name: string | null;
  status: string;
  metadata: Record<string, JsonValue>;
  created_at: string;
  updated_at: string;
  terminated_at: string | null;
  model_config: ModelConfigResponse | null;
  skills: SkillAssignmentResponse[];
  mcps: McpAssignmentResponse[];
  recent_job: JobSummary | null;
}

export interface SessionDetail extends SessionSummary {
  recent_jobs: JobSummary[];
}

export interface JobDetail extends JobSummary {
  prompt_run: PromptRunSummary;
  outputs: string[];
  events: JobEventResponse[];
  available_tools: SessionToolResponse[];
}

export interface SessionJobsResponse {
  jobs: JobSummary[];
  page: PageInfo;
}

export interface GameSessionMetadata {
  session_id: string;
  plugin_name: string;
  plugin_id: number;
  room_slug: string;
  created_at: string;
  frontend_url?: string | null;
}

export interface DashboardConfig {
  appName: string;
  dragncardsFrontendUrl: string;
  defaultProviderId: string;
  defaultModelName: string;
  defaultGamePlugin: string;
  defaultGameServiceMcpEnabled: boolean;
  defaultGameServiceMcpName: string;
  defaultGameServiceMcpTransport: string;
  defaultGameServiceMcpUrl: string;
  defaultSkills: string[];
  defaultCustomMcps: CustomMcpDraft[];
}

export interface CustomMcpDraft {
  name: string;
  transport: string;
  server_url: string;
  headers?: Record<string, string>;
}

export interface ReasoningDraft {
  enabled: boolean;
  effort: "low" | "medium" | "high";
  maxTokens: string;
}

export interface SessionDraft {
  name: string;
  providerId: string;
  modelName: string;
  reasoning: ReasoningDraft;
  gatewayOptionsText: string;
  providerOptionsText: string;
  selectedSkills: string[];
  createGameSession: boolean;
  gamePluginName: string;
  enableDefaultGameServiceMcp: boolean;
  customMcpsText: string;
}

export interface ContextMetadata {
  tokens_used: number;
  context_window_size: number;
  usage_ratio: number;
  compaction_count: number;
  last_compacted_at: string | null;
  multi_turn_memory: boolean;
}

export interface MergedOpenApiResult {
  document: Record<string, JsonValue>;
  errors: { service: string; message: string }[];
}
