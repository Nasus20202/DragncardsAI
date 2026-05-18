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
  description: string;
  metadata: Record<string, string>;
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

export interface McpRegistryResponse {
  name: string;
  transport: string;
  server_url: string;
  headers: Record<string, string>;
  custom: boolean;
  created_at: string;
}

export interface McpAssignmentResponse {
  name: string;
  transport: string;
  server_url: string;
  headers?: Record<string, string>;
  enabled: boolean;
  custom?: boolean;
}

export interface JobSummary {
  id: string;
  prompt: string;
  metadata: Record<string, JsonValue>;
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
  context_recent_message_limit: number | null;
  context_recent_tool_exchange_limit: number | null;
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
  outputs: string[];
  events: JobEventResponse[];
  available_tools: SessionToolResponse[];
}

export interface SessionJobsResponse {
  jobs: JobSummary[];
  page: PageInfo;
}

export interface DashboardConfig {
  appName: string;
  defaultProviderId: string;
  defaultModelName: string;
  defaultGameServiceMcpEnabled: boolean;
  defaultGameServiceMcpName: string;
  defaultGameServiceMcpTransport: string;
  defaultGameServiceMcpUrl: string;
  defaultSkills: string[];
  defaultCustomMcps: CustomMcpDraft[];
  dragncardsFrontendUrl: string;
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
  recentMessageLimit: string;
  recentToolExchangeLimit: string;
  reasoning: ReasoningDraft;
  gatewayOptionsText: string;
  providerOptionsText: string;
  selectedSkills: string[];
}

export interface ContextMetadata {
  tokens_used: number;
  context_window_size: number;
  usage_ratio: number;
  compaction_count: number;
  last_compacted_at: string | null;
  multi_turn_memory: boolean;
  token_breakdown: {
    system_prompt: number;
    replay: number;
    tools: number;
  };
}

export interface MergedOpenApiResult {
  document: Record<string, JsonValue>;
  errors: { service: string; message: string }[];
}

export interface GameSession {
  id: string;
  plugin: string;
  plugin_id: number;
  created_at: string;
  room_slug: string;
}
