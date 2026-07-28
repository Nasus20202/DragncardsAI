export type JsonValue =
  null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

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
  /** Per-seat roster; absent on sessions that are not running an orchestrated game. */
  players?: PlayerConfigResponse[];
  recent_job: JobSummary | null;
}

/**
 * One seat's agent configuration in an orchestrated multi-player game. Null
 * `provider_id` / `model_name` / `skills` mean the seat inherits the session's
 * own configuration, so two seats can differ on a single axis.
 */
export interface PlayerConfigResponse {
  player_id: string;
  display_name: string | null;
  provider_id: string | null;
  model_name: string | null;
  reasoning: { effort?: string; max_tokens?: number } | null;
  skills: string[] | null;
  gateway_options: Record<string, JsonValue>;
  provider_options: Record<string, JsonValue>;
  created_at: string;
  updated_at: string;
}

/** Request body for `PUT /sessions/{id}/players/{player_id}`. */
export interface PlayerConfigRequest {
  display_name?: string;
  provider_id?: string;
  model_name?: string;
  reasoning?: { enabled: boolean; effort?: string; max_tokens?: number };
  skills?: string[];
  gateway_options?: Record<string, JsonValue>;
  provider_options?: Record<string, JsonValue>;
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
  bifrostUiUrl: string;
  defaultReasoningEnabled: boolean;
  defaultReasoningEffort: "low" | "medium" | "high";
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

export type HistoryActor = "agent" | "game-service" | "evaluator" | "user";

export interface HistoryAgentPayload {
  intended_action?: string | null;
  reasoning?: string | null;
  arguments?: JsonValue;
  conversation_context?: JsonValue;
}

export interface HistoryGameServicePayload {
  state?: JsonValue;
  status?: string | null;
}

export interface HistoryEvaluatorScores {
  rules_legality?: number | null;
  strategic_quality?: number | null;
  tempo_efficiency?: number | null;
  threat_resource?: number | null;
}

export interface HistoryEvaluatorInfo {
  model?: string | null;
  provider?: string | null;
  evaluator_version?: string | null;
}

export interface HistoryEvaluatorPayload {
  scope?: string | null;
  target_seq?: number | null;
  round_span?: JsonValue;
  /**
   * The player this verdict pertains to (e.g. "player1"). `null`/absent only
   * for legacy/unattributed verdicts; per-player roll-ups and per-move targets
   * always set it.
   */
  player?: string | null;
  scores?: HistoryEvaluatorScores;
  overall_score?: number | null;
  rationale?: string | null;
  flags?: JsonValue;
  evaluator?: HistoryEvaluatorInfo;
}

// --- On-demand evaluation request / status (eval-service contract) ---

export type EvaluationScope = "move" | "round" | "game";

/** Per-target status as reported by the eval-service. */
export type EvaluationTargetStatus =
  "pending" | "running" | "completed" | "skipped" | "failed" | "cancelled";

/** Overall request status as reported by the eval-service. */
export type EvaluationRequestStatus =
  "pending" | "running" | "completed" | "partial" | "failed" | "cancelled";

/** Target selection sent with a `POST /games/{id}/evaluations` request. */
export interface EvaluationSelection {
  seqs?: number[];
  rounds?: number[];
  seq_range?: { from_seq: number; to_seq: number };
  whole_game?: boolean;
}

/** Reasoning override for the judge, mirroring the orchestrator's shape. */
export interface JudgeReasoning {
  enabled: boolean;
  effort?: "low" | "medium" | "high";
  max_tokens?: number | null;
}

/**
 * Per-request judge configuration. All fields are optional; omitted fields
 * fall back to the eval-service defaults. Empty fields MUST be omitted by the
 * client when assembling the request body.
 */
export interface JudgeConfig {
  provider_id?: string;
  model_name?: string;
  reasoning?: JudgeReasoning;
  prompt_override?: string;
  skills?: string[];
}

export interface EvaluationRequestBody {
  scope: EvaluationScope;
  selection: EvaluationSelection;
  force?: boolean;
  judge?: JudgeConfig;
}

export interface EvaluationTarget {
  target_seq: number;
  scope: EvaluationScope;
  round_span?: [number, number] | null;
  /** The player this target pertains to (e.g. "player1"); null for legacy. */
  player?: string | null;
  status: EvaluationTargetStatus;
  verdict?: HistoryEvaluatorPayload | null;
  error?: string | null;
}

/** Response from `POST /games/{id}/evaluations`. */
export interface EvaluationRequestAck {
  request_id: string;
  game_id: string;
  scope: EvaluationScope;
  created_count: number;
  skipped_count: number;
  targets: EvaluationTarget[];
}

/** Response from `GET /games/{id}/evaluations/{request_id}`. */
export interface EvaluationRequestStatusResponse {
  request_id: string;
  game_id: string;
  status: EvaluationRequestStatus;
  targets: EvaluationTarget[];
}

/** Response from `POST /games/{id}/evaluations/{request_id}/cancel`. */
export interface EvaluationCancelResponse {
  request_id: string;
  cancelled: number;
}

// --- Cross-game evaluations queue (eval-service `GET /evaluations`) ---

/**
 * Scope of an evaluation target as reported by the cross-game listing. Wider
 * than `EvaluationScope` (which only covers what the drawer can submit): the
 * listing also distinguishes "range" and "game" scopes.
 */
export type EvaluationQueueScope = "move" | "round" | "range" | "game";

/** A per-target summary in a queued evaluation request. */
export interface EvaluationQueueTarget {
  target_seq: number;
  scope: EvaluationQueueScope;
  round_span?: [number, number] | null;
  /** The player this target pertains to (e.g. "player1"); null for legacy. */
  player?: string | null;
  status: EvaluationTargetStatus;
}

/** A request summary from the cross-game `GET /evaluations` listing. */
export interface EvaluationQueueRequest {
  request_id: string;
  game_id: string;
  status: EvaluationRequestStatus;
  created_at: string;
  targets: EvaluationQueueTarget[];
}

/** Response from `GET /evaluations` (newest-first). */
export interface EvaluationQueueListResponse {
  requests: EvaluationQueueRequest[];
}

/** Response from `POST /evaluations/clear` (clear all terminal requests). */
export interface EvaluationClearResponse {
  deleted_count: number;
}

// --- Games with recorded history (history-service contract) ---

/** A single entry of `GET /history/games`. */
export interface HistoryGame {
  game_id: string;
  event_count: number;
  first_recorded_at: string;
  last_recorded_at: string;
}

/** Response from `DELETE /history/games/{game_id}`. */
export interface HistoryDeleteResponse {
  game_id: string;
  deleted_events: number;
  deleted_snapshots: number;
}

export interface HistoryEvent {
  seq: number;
  event_id: string;
  game_id: string;
  actor: HistoryActor;
  event_type: string;
  payload: HistoryAgentPayload &
    HistoryGameServicePayload &
    HistoryEvaluatorPayload &
    Record<string, JsonValue>;
  occurred_at: string;
  recorded_at: string;
}

export interface HistorySnapshot {
  snapshot_at_seq: number;
  recorded_at: string;
  [key: string]: JsonValue;
}

export type RestoreMode = "new" | "in_place";

export interface RestoreRequestBody {
  target_seq: number;
  mode: RestoreMode;
  /**
   * When true, the restore produces an EPHEMERAL, non-emitting session: it
   * records no history and is reaped server-side by TTL if the client never
   * tears it down. Used for the "open board at this event" reconstruction.
   */
  ephemeral?: boolean;
}

export interface RestoreOutcome {
  status?: string | null;
  target_seq?: number | null;
  mode?: RestoreMode | null;
  session_id?: string | null;
  message?: string | null;
  detail?: string | null;
  status_verified?: boolean | null;
  divergence?: string | null;
  [key: string]: JsonValue | undefined;
}
