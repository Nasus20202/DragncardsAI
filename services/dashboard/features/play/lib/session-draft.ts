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

/**
 * A new session starts unnamed on purpose. It used to start as a timestamp,
 * which told two sessions apart only by the minute they were created in, and the
 * dashboard then overwrote that with the first sixty characters of the first
 * prompt. Both are gone: the orchestrator names a session it finds unnamed when
 * it takes that session's first prompt, generating one name in one place and
 * storing it, so every client reads the same name rather than deriving its own.
 * A name typed here is still the user's and is never overwritten.
 */
const UNNAMED_SESSION = "";

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

  const reasoningOptions: Record<string, JsonValue> = {};
  if (reasoning.effort) {
    reasoningOptions.effort = reasoning.effort;
  }
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
    name: UNNAMED_SESSION,
    providerId: config.defaultProviderId,
    modelName: config.defaultModelName,
    recentMessageLimit: "",
    recentToolExchangeLimit: "",
    reasoning: buildDefaultReasoningDraft(config),
    gatewayOptionsText: safeJsonStringify({}),
    providerOptionsText: safeJsonStringify({}),
    selectedSkills: config.defaultSkills,
    defaultSubagentPersona: "",
    sessionPersona: "",
    // A new session allows no subagent persona. Deny-by-default is the only
    // starting point under which the empty control means what it shows: if a
    // fresh session allowed everything, ticking the first persona would silently
    // be a restriction rather than a grant.
    allowedSubagents: [],
    sessionMode: "chat",
  };
}

/**
 * A provider the user can actually select right now: marked available and
 * exposing at least one model.
 */
export const LEGACY_REASONING_EFFORTS = ["low", "medium", "high"] as const;

/**
 * Resolve the effort options advertised for one provider model. Missing
 * metadata, including a missing supported_efforts field, retains the legacy
 * options; an explicit empty list is authoritative and returns no options.
 */
export function reasoningEffortsForModel(
  provider: ProviderResponse | undefined,
  modelName: string
): string[] {
  const supportedEfforts =
    provider?.model_capabilities?.[modelName]?.reasoning?.supported_efforts;
  return supportedEfforts === undefined
    ? [...LEGACY_REASONING_EFFORTS]
    : [...supportedEfforts];
}

/**
 * Keep a draft's effort valid when its provider/model changes. An explicit
 * empty capability also disables reasoning because there is no selectable
 * effort to send.
 */
export function normalizeReasoningDraft(
  draft: ReasoningDraft,
  provider: ProviderResponse | undefined,
  modelName: string
): ReasoningDraft {
  const efforts = reasoningEffortsForModel(provider, modelName);
  const effort = efforts.includes(draft.effort) ? draft.effort : efforts[0] ?? "";
  const enabled = efforts.length > 0 && draft.enabled;
  if (enabled === draft.enabled && effort === draft.effort) {
    return draft;
  }
  return { ...draft, enabled, effort };
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
 * Re-point a draft at a provider/model the user can actually use right now.
 *
 * Keeps the draft's own provider when that provider is working, clamping the
 * model to the ones it currently offers; otherwise falls back to
 * {@link pickDefaultProviderModel}. An empty {@link providers} list means the
 * catalog has not been loaded (or failed to load), which is no evidence that the
 * draft's provider is broken — the draft is then returned untouched so a
 * degraded catalog cannot silently reset the user's provider and model.
 */
export function withUsableProviderModel(
  config: DashboardConfig,
  draft: SessionDraft,
  providers: ProviderResponse[]
): SessionDraft {
  const current = providers.find(
    (provider) => provider.provider_id === draft.providerId
  );
  if (current !== undefined && isWorking(current)) {
    return {
      ...draft,
      modelName: clampModelToProvider(current, draft.modelName),
    };
  }

  if (providers.length === 0) {
    return draft;
  }

  const { providerId, modelName } = pickDefaultProviderModel(config, providers);
  return { ...draft, providerId, modelName };
}

/**
 * Build the draft for a brand-new session. Carries forward the user's
 * last-used settings (provider, model, reasoning, skills, replay limits, and
 * advanced/MCP options) from {@link lastUsed} when available, falling back to
 * the configuration defaults when there is no prior draft to copy from. The
 * session name is never carried: a new session starts unnamed and is named from
 * its first prompt.
 *
 * The carried provider/model is validated against the currently available
 * {@link providers} by {@link withUsableProviderModel} so a new session is never
 * pinned to a broken provider.
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
    name: UNNAMED_SESSION,
    reasoning: { ...lastUsed.reasoning },
    selectedSkills: [...lastUsed.selectedSkills],
    allowedSubagents: [...(lastUsed.allowedSubagents ?? [])],
  };

  return withUsableProviderModel(config, carried, providers);
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
    defaultSubagentPersona: session.default_subagent_persona ?? "",
    sessionPersona: session.session_persona ?? "",
    // A response that predates the field carries no allowlist, and an absent
    // allowlist is an empty one — the same thing the orchestrator means by it.
    allowedSubagents: session.allowed_subagents ?? [],
    sessionMode: session.session_mode ?? "chat",
  };
}

/**
 * The message to show when the orchestrator did not store what a session write
 * asked it to store, or `null` when everything asked for is in place.
 *
 * A write is only as good as what the server ends up holding, and the dashboard
 * already re-reads the session afterwards — so it holds both halves and can
 * simply compare them. Without the comparison a discarded setting is reported as
 * a successful save, which on an allowlist governing what the agent may spawn
 * leaves the user believing they narrowed something they did not.
 *
 * **A field missing from the response counts as not applied, never as cleared.**
 * An orchestrator predating a setting answers `200 OK` and omits the field, which
 * is byte-for-byte what "cleared" looks like; conflating the two is precisely how
 * a discarded write passes for a successful one. Nothing here reads a version
 * number: this tests whether the setting took effect, so it covers a refusal that
 * has nothing to do with version skew just as well.
 *
 * Only the session persona and the subagent allowlist are compared. They are the
 * settings whose absence from a response is indistinguishable from an empty
 * value; the rest of the panel's fields are echoed by every orchestrator that
 * ever accepted them, or fail loudly on their own.
 */
export function unappliedSessionSettings(
  requested: Pick<SessionDraft, "sessionPersona" | "allowedSubagents">,
  saved: Pick<SessionDetail, "session_persona" | "allowed_subagents">
): string | null {
  const unapplied: string[] = [];

  if ((requested.sessionPersona || "") !== (saved.session_persona ?? "")) {
    unapplied.push("the session persona");
  }

  // Compared as sets: the orchestrator reports the allowlist sorted, and an
  // ordering difference is not a lost setting.
  const savedAllowed = new Set(saved.allowed_subagents ?? []);
  const requestedAllowed = new Set(requested.allowedSubagents);
  if (
    savedAllowed.size !== requestedAllowed.size ||
    [...requestedAllowed].some((name) => !savedAllowed.has(name))
  ) {
    unapplied.push("the allowed subagents");
  }

  if (unapplied.length === 0) {
    return null;
  }

  return (
    `The server did not apply ${unapplied.join(" or ")}. The ` +
    "agent-orchestrator is most likely older than this dashboard — rebuild and " +
    "restart it so both are on the same version."
  );
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
