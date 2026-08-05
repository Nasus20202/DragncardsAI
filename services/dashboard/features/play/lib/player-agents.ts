import {
  PlayerConfigRequest,
  PlayerConfigResponse,
} from "@/features/shared/lib/types";

/** The Marvel Champions seats an orchestrated game can fill. */
export const PLAYER_SEATS = [
  "player1",
  "player2",
  "player3",
  "player4",
] as const;

export type PlayerSeat = (typeof PLAYER_SEATS)[number];

/** Two heroes is the default table for comparing one configuration against another. */
export const DEFAULT_PLAYER_SEAT_COUNT = 2;

/**
 * Editable per-seat state. Every field is a string / flag so it maps directly
 * onto form controls; empty means "inherit from the session", which is what
 * makes "same configuration except one axis" the easy thing to express.
 */
export interface PlayerAgentDraft {
  playerId: string;
  displayName: string;
  providerId: string;
  modelName: string;
  reasoningEnabled: boolean;
  reasoningEffort: "low" | "medium" | "high";
  reasoningMaxTokens: string;
  /**
   * Persona name, or `""` for "no persona" — the seat then copies the session.
   * The orchestrator snapshots it once, when the seat's own session is created,
   * so editing it changes only seats that have not played yet.
   */
  persona: string;
  /** `null` inherits the session's skills; an array overrides them. */
  selectedSkills: string[] | null;
}

export function isPlayerSeat(value: string): value is PlayerSeat {
  return (PLAYER_SEATS as readonly string[]).includes(value);
}

/** An empty draft for a seat — everything inherited. */
export function createDefaultPlayerAgentDraft(
  playerId: string
): PlayerAgentDraft {
  return {
    playerId,
    displayName: "",
    providerId: "",
    modelName: "",
    reasoningEnabled: false,
    reasoningEffort: "medium",
    reasoningMaxTokens: "",
    persona: "",
    selectedSkills: null,
  };
}

/** The default two-seat roster. */
export function createDefaultRoster(
  seatCount: number = DEFAULT_PLAYER_SEAT_COUNT
): PlayerAgentDraft[] {
  return PLAYER_SEATS.slice(
    0,
    Math.max(1, Math.min(seatCount, PLAYER_SEATS.length))
  ).map(createDefaultPlayerAgentDraft);
}

/** Hydrate a draft from a persisted seat configuration. */
export function buildDraftFromPlayerConfig(
  config: PlayerConfigResponse
): PlayerAgentDraft {
  const effort = config.reasoning?.effort;
  return {
    playerId: config.player_id,
    displayName: config.display_name ?? "",
    providerId: config.provider_id ?? "",
    modelName: config.model_name ?? "",
    reasoningEnabled: config.reasoning !== null,
    reasoningEffort:
      effort === "low" || effort === "high" || effort === "medium"
        ? effort
        : "medium",
    reasoningMaxTokens:
      config.reasoning?.max_tokens === undefined
        ? ""
        : String(config.reasoning.max_tokens),
    persona: config.persona ?? "",
    selectedSkills: config.skills === null ? null : [...config.skills],
  };
}

/**
 * Assemble the request body for a seat, OMITTING unset fields so the server
 * applies inheritance rather than us freezing the session's current values into
 * the seat. `reasoning` is always sent when the draft is loaded, because
 * "reasoning off" has to be expressible, not just absent.
 */
export function assemblePlayerAgentConfig(
  draft: PlayerAgentDraft
): PlayerConfigRequest {
  const body: PlayerConfigRequest = {};

  const displayName = draft.displayName.trim();
  if (displayName) {
    body.display_name = displayName;
  }
  const providerId = draft.providerId.trim();
  if (providerId) {
    body.provider_id = providerId;
  }
  const modelName = draft.modelName.trim();
  if (modelName) {
    body.model_name = modelName;
  }
  const persona = draft.persona.trim();
  if (persona) {
    body.persona = persona;
  }

  if (draft.reasoningEnabled) {
    body.reasoning = { enabled: true, effort: draft.reasoningEffort };
    const maxTokens = draft.reasoningMaxTokens.trim();
    if (maxTokens) {
      const parsed = Number(maxTokens);
      if (Number.isInteger(parsed) && parsed > 0) {
        body.reasoning.max_tokens = parsed;
      }
    }
  } else {
    body.reasoning = { enabled: false };
  }

  if (draft.selectedSkills !== null) {
    body.skills = [...draft.selectedSkills];
  }

  return body;
}

/**
 * A short human-readable summary of what a seat will run with, used to show at
 * a glance how two configurations differ. Inherited values read as "inherited"
 * rather than being silently resolved on the client.
 */
export function describePlayerAgentDraft(draft: PlayerAgentDraft): string {
  const model = draft.modelName.trim() || "inherited model";
  const provider = draft.providerId.trim() || "inherited provider";
  const reasoning = draft.reasoningEnabled
    ? `reasoning ${draft.reasoningEffort}`
    : "no reasoning";
  const skills =
    draft.selectedSkills === null
      ? "inherited skills"
      : `${draft.selectedSkills.length} skill(s)`;
  return `${provider} / ${model} / ${reasoning} / ${skills}`;
}
