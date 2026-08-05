"use client";

import { Button } from "@heroui/react";
import { useEffect, useMemo, useState } from "react";

import { listPersonas, setPlayerAgent } from "@/features/play/lib/client-api";
import {
  assemblePlayerAgentConfig,
  buildDraftFromPlayerConfig,
  createDefaultPlayerAgentDraft,
  PLAYER_SEATS,
  PlayerAgentDraft,
} from "@/features/play/lib/player-agents";
import { SelectField } from "@/features/shared/components/form-fields";
import {
  PersonaResponse,
  PlayerConfigResponse,
} from "@/features/shared/lib/types";

/** The option meaning "this seat names no persona" — it copies the session. */
const NO_PERSONA_VALUE = "";
const NO_PERSONA_LABEL = "No persona (copies the session)";
/** The option meaning "this seat runs the session's own model". */
const INHERIT_MODEL_VALUE = "";

/**
 * The seats of an orchestrated session, and the two axes a user varies between
 * them: the persona a seat plays with and the model it plays on.
 *
 * Only shown for an orchestrated session — a chat session has no seats. A seat
 * has to exist before the orchestrator will prompt it (`prompt_player_agent`
 * refuses an unconfigured seat), so this is also where a seat is added; removal
 * is deliberately not offered here, because deleting a seat terminates the
 * agent session it owns and that destruction wants its own confirmation.
 *
 * A saved seat is kept in local state from the orchestrator's own response, so
 * an edit shows immediately without waiting for the session to be re-fetched.
 * The panel remounts this component per session, so one session's seats can
 * never be shown under another's.
 */
export function SeatRoster({
  sessionId,
  players,
  modelOptions,
  sessionModelName,
  onOpenSeatContext,
}: {
  /** `null` before the session exists; seats are stored per session. */
  sessionId: string | null;
  players: PlayerConfigResponse[];
  /** The models the session's provider offers, as the model picker lists them. */
  modelOptions: string[];
  /** The session's own model, named so "inherited" says what it inherits. */
  sessionModelName: string;
  /** Opens a seat's own session, whose transcript is that seat's context. */
  onOpenSeatContext?: (seatSessionId: string) => void;
}) {
  const [personas, setPersonas] = useState<PersonaResponse[]>([]);
  const [saved, setSaved] = useState<PlayerConfigResponse[]>([]);
  const [pendingSeat, setPendingSeat] = useState<string | null>(null);
  const [errorText, setErrorText] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    // A failed load leaves the catalogue empty: a seat can still be set back to
    // no persona, and one already naming a persona still shows it.
    listPersonas()
      .then((loaded) => {
        if (!cancelled) {
          setPersonas(loaded);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPersonas([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const seats = useMemo(() => {
    const byId = new Map<string, PlayerConfigResponse>();
    for (const seat of players) {
      byId.set(seat.player_id, seat);
    }
    for (const seat of saved) {
      byId.set(seat.player_id, seat);
    }
    return [...byId.values()].sort((left, right) =>
      left.player_id.localeCompare(right.player_id)
    );
  }, [players, saved]);

  const nextFreeSeat = PLAYER_SEATS.find(
    (candidate) => !seats.some((seat) => seat.player_id === candidate)
  );

  async function writeSeat(playerId: string, draft: PlayerAgentDraft) {
    if (!sessionId) {
      return;
    }
    setPendingSeat(playerId);
    setErrorText(null);
    try {
      const next = await setPlayerAgent(
        sessionId,
        playerId,
        assemblePlayerAgentConfig(draft)
      );
      setSaved((current) => [
        ...current.filter((seat) => seat.player_id !== playerId),
        next,
      ]);
    } catch (error) {
      setErrorText(
        error instanceof Error ? error.message : "Failed to save the seat"
      );
    } finally {
      setPendingSeat(null);
    }
  }

  function editSeat(
    seat: PlayerConfigResponse,
    change: Partial<PlayerAgentDraft>
  ) {
    // The whole seat is sent because the orchestrator's PUT replaces it, so an
    // edit to one axis must carry the rest of the seat unchanged.
    void writeSeat(seat.player_id, {
      ...buildDraftFromPlayerConfig(seat),
      ...change,
    });
  }

  function personaItems(seat: PlayerConfigResponse) {
    const items = [
      { value: NO_PERSONA_VALUE, label: NO_PERSONA_LABEL },
      ...personas.map((persona) => ({
        value: persona.name,
        label: persona.display_name
          ? `${persona.name} — ${persona.display_name}`
          : persona.name,
      })),
    ];
    const current = seat.persona ?? "";
    if (current && !personas.some((persona) => persona.name === current)) {
      items.push({ value: current, label: current });
    }
    return items;
  }

  function modelItems(seat: PlayerConfigResponse) {
    const items = [
      {
        value: INHERIT_MODEL_VALUE,
        label: sessionModelName
          ? `Inherited (${sessionModelName})`
          : "Inherited from the session",
      },
      ...modelOptions.map((model) => ({ value: model, label: model })),
    ];
    const current = seat.model_name ?? "";
    if (current && !modelOptions.includes(current)) {
      items.push({ value: current, label: current });
    }
    return items;
  }

  return (
    <div className="grid gap-2" data-testid="seat-roster">
      <p className="text-xs font-semibold uppercase tracking-wider text-default-400">
        Player seats
      </p>

      {!sessionId && (
        <p className="text-xs text-default-500">
          Create the session to configure its seats.
        </p>
      )}

      {sessionId && seats.length === 0 && (
        <p className="text-xs text-default-500">
          No seats configured yet. The orchestrator can only prompt a seat that
          exists, so add one per hero at the table.
        </p>
      )}

      {errorText && (
        <p className="text-xs text-danger" role="alert">
          {errorText}
        </p>
      )}

      {seats.map((seat) => {
        const seatSessionId = seat.agent_session_id ?? "";
        return (
          <div
            key={seat.player_id}
            data-testid={`seat-row-${seat.player_id}`}
            className="grid gap-2 rounded-lg border border-default-200/60 px-3 py-2"
          >
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-sm font-medium text-foreground">
                {seat.player_id}
              </span>
              {seat.display_name && (
                <span className="truncate text-xs text-default-500">
                  {seat.display_name}
                </span>
              )}
            </div>

            <SelectField
              id={`seat-persona-${seat.player_id}`}
              label="Persona"
              ariaLabel={`Persona for ${seat.player_id}`}
              items={personaItems(seat)}
              value={seat.persona ?? ""}
              disabled={pendingSeat === seat.player_id}
              triggerTestId={`seat-persona-trigger-${seat.player_id}`}
              onChange={(persona) => editSeat(seat, { persona })}
            />

            <SelectField
              id={`seat-model-${seat.player_id}`}
              label="Model"
              ariaLabel={`Model for ${seat.player_id}`}
              items={modelItems(seat)}
              value={seat.model_name ?? ""}
              disabled={pendingSeat === seat.player_id}
              triggerTestId={`seat-model-trigger-${seat.player_id}`}
              onChange={(modelName) => editSeat(seat, { modelName })}
            />

            {seatSessionId ? (
              <Button
                aria-label={`Open the context of ${seat.player_id}`}
                data-testid={`seat-context-${seat.player_id}`}
                size="sm"
                variant="ghost"
                onPress={() => onOpenSeatContext?.(seatSessionId)}
              >
                Open this seat&apos;s context
              </Button>
            ) : (
              <p
                className="text-xs text-default-500"
                data-testid={`seat-no-context-${seat.player_id}`}
              >
                No context yet — this seat has not been prompted.
              </p>
            )}
          </div>
        );
      })}

      {sessionId && nextFreeSeat && (
        <Button
          aria-label={`Add seat ${nextFreeSeat}`}
          data-testid="seat-roster-add"
          isDisabled={pendingSeat !== null}
          size="sm"
          variant="ghost"
          onPress={() =>
            void writeSeat(
              nextFreeSeat,
              createDefaultPlayerAgentDraft(nextFreeSeat)
            )
          }
        >
          Add {nextFreeSeat}
        </Button>
      )}
    </div>
  );
}
