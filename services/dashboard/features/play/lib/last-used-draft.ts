import { SessionDraft } from "@/features/shared/lib/types";

/**
 * Browser-local memory of the configuration the user last committed (provider,
 * model, reasoning, skills, replay limits, advanced JSON), so that creating a
 * session after a page reload starts from those settings instead of snapping
 * back to the dashboard defaults.
 *
 * This is a per-browser UI preference, not service state — it follows the
 * dashboard's existing `localStorage` pattern (the selected session id in
 * `use-play-session.ts`, the theme in `features/shell`) rather than adding a
 * server-side store, which would make one user's last choice leak into every
 * other browser. The session name is deliberately not persisted: every new
 * session gets a freshly generated one.
 */
const STORAGE_KEY = "play:lastUsedDraft";

function isStringArray(value: unknown): value is string[] {
  return (
    Array.isArray(value) && value.every((item) => typeof item === "string")
  );
}

function isReasoningDraft(value: unknown): value is SessionDraft["reasoning"] {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.enabled === "boolean" &&
    (candidate.effort === "low" ||
      candidate.effort === "medium" ||
      candidate.effort === "high") &&
    typeof candidate.maxTokens === "string"
  );
}

/**
 * Validate a parsed storage payload. Anything written by an older dashboard
 * build — or hand-edited — is rejected wholesale rather than partially trusted,
 * so a stale shape can never crash the workspace on load.
 */
function parseDraft(raw: unknown): SessionDraft | null {
  if (typeof raw !== "object" || raw === null) {
    return null;
  }
  const candidate = raw as Record<string, unknown>;
  if (
    typeof candidate.providerId !== "string" ||
    typeof candidate.modelName !== "string" ||
    typeof candidate.recentMessageLimit !== "string" ||
    typeof candidate.recentToolExchangeLimit !== "string" ||
    typeof candidate.gatewayOptionsText !== "string" ||
    typeof candidate.providerOptionsText !== "string" ||
    !isReasoningDraft(candidate.reasoning) ||
    !isStringArray(candidate.selectedSkills)
  ) {
    return null;
  }

  return {
    name: "",
    providerId: candidate.providerId,
    modelName: candidate.modelName,
    recentMessageLimit: candidate.recentMessageLimit,
    recentToolExchangeLimit: candidate.recentToolExchangeLimit,
    reasoning: { ...candidate.reasoning },
    gatewayOptionsText: candidate.gatewayOptionsText,
    providerOptionsText: candidate.providerOptionsText,
    selectedSkills: [...candidate.selectedSkills],
    // Tolerated rather than required: a draft written before personas existed
    // is still perfectly usable, and defaults to no persona.
    defaultSubagentPersona:
      typeof candidate.defaultSubagentPersona === "string"
        ? candidate.defaultSubagentPersona
        : "",
    // Likewise tolerated: a draft written before session modes existed — or one
    // carrying a mode this build does not know — falls back to the default.
    sessionMode:
      candidate.sessionMode === "chat" ||
      candidate.sessionMode === "orchestrated"
        ? candidate.sessionMode
        : "chat",
  };
}

/** The last committed configuration, or `null` when there is nothing usable. */
export function readLastUsedDraft(): SessionDraft | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      return null;
    }
    return parseDraft(JSON.parse(stored) as unknown);
  } catch {
    // Unparseable or unavailable storage is never fatal: fall back to defaults.
    return null;
  }
}

/**
 * Remember a configuration the user actually committed to the orchestrator.
 * Called from the commit paths only, so a half-typed JSON textarea is never
 * persisted as the starting point for the next session.
 */
export function writeLastUsedDraft(draft: SessionDraft): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ ...draft, name: "" })
    );
  } catch {
    // Storage can be full or blocked; losing the preference is acceptable.
  }
}
