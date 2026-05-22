import {
  CustomMcpDraft,
  DashboardConfig,
  JsonValue,
  ReasoningDraft,
  SessionDetail,
  SessionDraft,
} from "@/features/shared/lib/types";

export function buildDefaultSessionName(now = new Date()): string {
  return now
    .toLocaleString("en-CA", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    })
    .replace(",", "");
}

function safeJsonStringify(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function isRecord(
  value: JsonValue | undefined
): value is Record<string, JsonValue> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function buildDefaultReasoningDraft(config: DashboardConfig): ReasoningDraft {
  return {
    enabled: config.defaultReasoningEnabled,
    effort: config.defaultReasoningEffort,
    maxTokens: "",
  };
}

function formatOptionalInteger(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value)
    ? String(value)
    : "";
}

export function parseOptionalPositiveInteger(
  value: string,
  label: string
): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  const parsed = Number(trimmed);
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new Error(`${label} must be a non-negative integer`);
  }
  return parsed === 0 ? null : parsed;
}

function extractReasoningDraft(
  options: Record<string, JsonValue>,
  config: DashboardConfig
): ReasoningDraft {
  const raw = options.reasoning;
  if (!isRecord(raw)) {
    return {
      enabled: false,
      effort: config.defaultReasoningEffort,
      maxTokens: "",
    };
  }

  const effort = raw.effort;
  const maxTokens = raw.max_tokens;
  return {
    enabled: true,
    effort:
      effort === "low" || effort === "medium" || effort === "high"
        ? effort
        : "medium",
    maxTokens:
      typeof maxTokens === "number" && Number.isFinite(maxTokens)
        ? String(maxTokens)
        : "",
  };
}

export function applyReasoningToGatewayOptions(
  gatewayOptions: Record<string, JsonValue>,
  reasoning: ReasoningDraft
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
  return {
    name: buildDefaultSessionName(),
    providerId: config.defaultProviderId,
    modelName: config.defaultModelName,
    recentMessageLimit: "",
    recentToolExchangeLimit: "",
    reasoning: buildDefaultReasoningDraft(config),
    gatewayOptionsText: safeJsonStringify({}),
    providerOptionsText: safeJsonStringify({}),
    selectedSkills: config.defaultSkills,
  };
}

export function buildDraftFromSession(
  config: DashboardConfig,
  session: SessionDetail
): SessionDraft {
  const defaultDraft = createDefaultDraft(config);

  return {
    ...defaultDraft,
    name: session.name ?? "",
    providerId: session.model_config?.provider_id ?? defaultDraft.providerId,
    modelName: session.model_config?.model_name ?? defaultDraft.modelName,
    recentMessageLimit: formatOptionalInteger(
      session.context_recent_message_limit
    ),
    recentToolExchangeLimit: formatOptionalInteger(
      session.context_recent_tool_exchange_limit
    ),
    reasoning: extractReasoningDraft(
      session.model_config?.gateway_options ?? {},
      config
    ),
    gatewayOptionsText: safeJsonStringify(
      session.model_config?.gateway_options ?? {}
    ),
    providerOptionsText: safeJsonStringify(
      session.model_config?.provider_options ?? {}
    ),
    selectedSkills: session.skills.map((skill) => skill.skill_name),
  };
}

export function parseJsonObject(
  text: string,
  label: string
): Record<string, JsonValue> {
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
