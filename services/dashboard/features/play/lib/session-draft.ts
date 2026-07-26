import {
  CustomMcpDraft,
  DashboardConfig,
  JsonValue,
  ProviderResponse,
  ReasoningDraft,
  SessionDetail,
  SessionDraft,
  SessionSummary,
} from "@/features/shared/lib/types";

/**
 * Whether a session should appear in the sidebar and be eligible for
 * (re)selection: not terminated and not a subagent-child session. Shared
 * between the sidebar render filter and post-removal reselection so the two
 * cannot drift.
 */
export function isSelectableSession(
  session: SessionSummary,
  subagentChildSessionIds: Set<string>
): boolean {
  return (
    session.status !== "terminated" && !subagentChildSessionIds.has(session.id)
  );
}

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

/**
 * A provider the user can actually select right now: marked available and
 * exposing at least one model.
 */
export function isWorking(provider: ProviderResponse): boolean {
  return provider.available !== false && provider.models.length > 0;
}

/**
 * Clamp a model name to the provider's offered models, falling back to the
 * provider's first model when the requested name is no longer offered.
 */
export function clampModelToProvider(
  provider: ProviderResponse,
  modelName: string
): string {
  return provider.models.includes(modelName) ? modelName : provider.models[0];
}

/**
 * Pick a usable default provider/model for an initial draft. Prefers the
 * configured default provider when it is working, then any other working
 * provider that exposes models, so that the selectors default to a provider
 * the user can actually use even when some providers are unavailable.
 */
export function pickDefaultProviderModel(
  config: DashboardConfig,
  providers: ProviderResponse[]
): { providerId: string; modelName: string } {
  const fallback = {
    providerId: config.defaultProviderId,
    modelName: config.defaultModelName,
  };

  const configured = providers.find(
    (provider) => provider.provider_id === config.defaultProviderId
  );
  if (configured && isWorking(configured)) {
    return {
      providerId: configured.provider_id,
      modelName: clampModelToProvider(configured, config.defaultModelName),
    };
  }

  const working = providers.find(isWorking);
  if (working) {
    return {
      providerId: working.provider_id,
      modelName: working.models[0],
    };
  }

  return fallback;
}

/**
 * Build the draft for a brand-new session. Carries forward the user's
 * last-used settings (provider, model, reasoning, skills, replay limits, and
 * advanced/MCP options) from {@link lastUsed} when available, falling back to
 * the configuration defaults when there is no prior draft to copy from. Only
 * the session name is always freshly generated.
 *
 * The carried provider/model is validated against the currently available
 * {@link providers}: when the prior provider is now unavailable or exposes no
 * usable model, the provider/model fall back to {@link pickDefaultProviderModel}
 * so a new session is never pinned to a broken provider.
 */
export function createNewSessionDraft(
  config: DashboardConfig,
  lastUsed: SessionDraft | null,
  providers: ProviderResponse[] = []
): SessionDraft {
  if (!lastUsed) {
    return createDefaultDraft(config);
  }

  const carried: SessionDraft = {
    ...lastUsed,
    name: buildDefaultSessionName(),
    reasoning: { ...lastUsed.reasoning },
    selectedSkills: [...lastUsed.selectedSkills],
  };

  const carriedProvider = providers.find(
    (provider) => provider.provider_id === carried.providerId
  );
  if (carriedProvider !== undefined && isWorking(carriedProvider)) {
    // Clamp the carried model so a stale name the provider no longer offers
    // can't pass through.
    return {
      ...carried,
      modelName: clampModelToProvider(carriedProvider, carried.modelName),
    };
  }

  const { providerId, modelName } = pickDefaultProviderModel(config, providers);
  return { ...carried, providerId, modelName };
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
