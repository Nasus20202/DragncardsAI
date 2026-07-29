"use client";

import { Button, Chip, Spinner } from "@heroui/react";
import { useState } from "react";

import { dragncardsRoomUrl } from "@/features/shared/lib/dragncards";
import { RestoreMode, RestoreOutcome } from "@/features/shared/lib/types";

export interface RestoreControlProps {
  targetSeq: number | null;
  onRestore: (targetSeq: number, mode: RestoreMode) => Promise<RestoreOutcome>;
  /**
   * DragnCards frontend base URL, used to link straight to the room a branch
   * restore creates. Without it the outcome still names the room, it just is not
   * clickable.
   */
  frontendUrl?: string;
}

type Outcome =
  | { kind: "success"; outcome: RestoreOutcome; mode: RestoreMode }
  | {
      kind: "warning";
      outcome: RestoreOutcome;
      mode: RestoreMode;
      divergence: string;
    }
  | { kind: "failure"; message: string }
  | null;

/** The room a restore reported, or null. Empty is treated as absent. */
function roomSlug(outcome: RestoreOutcome): string | null {
  return typeof outcome.room_slug === "string" && outcome.room_slug.length > 0
    ? outcome.room_slug
    : null;
}

/**
 * What a completed restore did, in the user's terms. The two modes produce
 * different things and so read differently: an in-place rewind changes the game
 * the user was already looking at, while a branch restore produces a *new* game
 * that has to be found before it is any use.
 */
function describeOutcome(outcome: RestoreOutcome, mode: RestoreMode): string {
  if (typeof outcome.message === "string" && outcome.message.length > 0) {
    return outcome.message;
  }
  if (mode === "in_place") {
    return "This game has been rewound to the selected moment.";
  }
  const slug = roomSlug(outcome);
  if (slug) {
    return `New game created: ${slug}.`;
  }
  if (typeof outcome.session_id === "string" && outcome.session_id.length > 0) {
    return `New game created (session ${outcome.session_id}).`;
  }
  return "Restore completed.";
}

/**
 * The room a branch restore created, when it named one. Returned separately from
 * the message so it can be rendered as a link rather than as text.
 */
function newRoomUrl(
  outcome: RestoreOutcome,
  mode: RestoreMode,
  frontendUrl: string | undefined
): string | null {
  if (mode !== "new" || !frontendUrl) return null;
  const slug = roomSlug(outcome);
  return slug ? dragncardsRoomUrl(frontendUrl, slug) : null;
}

/**
 * The agent-context note the service reports when it restored the board but not
 * the agent conversation. This is information, not failure: a game whose agent
 * session has since been terminated has none to resume, which is the normal
 * state of anything being browsed in history.
 */
function agentNote(outcome: RestoreOutcome): string | null {
  if (outcome.agent_context_restored) return null;
  return typeof outcome.agent_context_note === "string" &&
    outcome.agent_context_note.length > 0
    ? outcome.agent_context_note
    : null;
}

export function RestoreControl({
  targetSeq,
  onRestore,
  frontendUrl,
}: RestoreControlProps) {
  const [mode, setModeState] = useState<RestoreMode>("new");
  const [confirmed, setConfirmed] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);
  const [outcome, setOutcome] = useState<Outcome>(null);
  const [lastTargetSeq, setLastTargetSeq] = useState<number | null>(targetSeq);

  // Reset the pending confirmation/outcome when the selected moment changes.
  // (Adjusting state during render is React's recommended pattern over an
  // effect for "reset on prop change".)
  if (targetSeq !== lastTargetSeq) {
    setLastTargetSeq(targetSeq);
    setConfirmed(false);
    setOutcome(null);
  }

  const setMode = (next: RestoreMode) => {
    setModeState(next);
    setConfirmed(false);
    setOutcome(null);
  };

  const disabled = targetSeq === null;
  const needsConfirm = mode === "in_place" && !confirmed;

  const handleRestore = async () => {
    if (targetSeq === null) return;
    if (needsConfirm) {
      setConfirmed(true);
      return;
    }
    setIsRestoring(true);
    setOutcome(null);
    try {
      const result = await onRestore(targetSeq, mode);
      const failed =
        typeof result.status === "string" &&
        ["failed", "error"].includes(result.status.toLowerCase());
      if (failed) {
        setOutcome({
          kind: "failure",
          message:
            (typeof result.detail === "string" && result.detail) ||
            (typeof result.message === "string" && result.message) ||
            "Restore failed.",
        });
      } else {
        // A 2xx restore can still be degraded: the upstream reports it could
        // not verify the resulting status, or that the restored state diverged
        // from what was expected. Surface that as a warning rather than a
        // clean success.
        const divergence =
          typeof result.divergence === "string" && result.divergence.length > 0
            ? result.divergence
            : null;
        if (result.status_verified === false || divergence) {
          setOutcome({
            kind: "warning",
            outcome: result,
            mode,
            divergence:
              divergence ?? "Restore could not be verified against the target.",
          });
        } else {
          setOutcome({ kind: "success", outcome: result, mode });
        }
      }
    } catch (e) {
      setOutcome({
        kind: "failure",
        message: e instanceof Error ? e.message : "Restore failed.",
      });
    } finally {
      setIsRestoring(false);
    }
  };

  return (
    <div
      className="flex flex-col gap-3 border-t border-default-200/60 p-4"
      data-testid="restore-control"
    >
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-foreground">
          Restore play
        </span>
        {targetSeq === null ? (
          <span className="text-xs text-default-400">
            Select a moment to restore to.
          </span>
        ) : (
          <Chip size="sm" variant="soft" color="default">
            Target #{targetSeq}
          </Chip>
        )}
      </div>
      <p className="text-xs text-default-400">
        Puts a playable game back at this moment. Pick where that game should
        be.
      </p>

      <fieldset
        className="flex flex-col gap-2"
        aria-label="Restore target mode"
      >
        <label className="flex items-start gap-2 text-sm">
          <input
            type="radio"
            name="restore-mode"
            value="new"
            checked={mode === "new"}
            disabled={disabled}
            onChange={() => setMode("new")}
            className="mt-1"
          />
          <span>
            <span className="flex items-center gap-1.5">
              <span className="font-medium text-foreground">
                Into a new game
              </span>
              <Chip size="sm" variant="soft" color="success">
                Safe
              </Chip>
            </span>
            <span className="block text-xs text-default-400">
              Creates a separate DragnCards game with its own history, starting
              from this moment. This game is not changed.
            </span>
          </span>
        </label>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="radio"
            name="restore-mode"
            value="in_place"
            checked={mode === "in_place"}
            disabled={disabled}
            onChange={() => setMode("in_place")}
            className="mt-1"
          />
          <span>
            <span className="flex items-center gap-1.5">
              <span className="font-medium text-foreground">
                Over this game
              </span>
              <Chip size="sm" variant="soft" color="danger">
                Destructive
              </Chip>
            </span>
            <span className="block text-xs text-default-400">
              Rewinds the live game itself to this moment. Everything played
              after it is gone.
            </span>
          </span>
        </label>
      </fieldset>

      {mode === "in_place" && (
        <div
          role="alert"
          data-testid="restore-in-place-warning"
          className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger"
        >
          Warning: game state recorded after the selected moment will be
          discarded. This cannot be undone.
        </div>
      )}

      <Button
        type="button"
        variant={mode === "in_place" ? "danger" : "primary"}
        isDisabled={disabled || isRestoring}
        data-testid="restore-submit"
        onPress={handleRestore}
      >
        {/*
          The label names the action first and only becomes a confirmation once
          the user has asked for it. The reverse — opening on "Confirm overwrite"
          and changing to the action name after the first click — read as though
          something had already been armed, and gave the destructive step its
          scariest wording at the moment it was least earned.
        */}
        {isRestoring ? (
          <Spinner size="sm" />
        ) : mode !== "in_place" ? (
          "Create the new game"
        ) : confirmed ? (
          "Confirm overwrite"
        ) : (
          "Rewind this game"
        )}
      </Button>

      {(outcome?.kind === "success" || outcome?.kind === "warning") && (
        <div
          role="status"
          data-testid={
            outcome.kind === "success" ? "restore-success" : "restore-warning"
          }
          className={
            outcome.kind === "success"
              ? "flex flex-col gap-1 rounded-lg border border-success/30 bg-success/10 px-3 py-2 text-xs text-success"
              : "flex flex-col gap-1 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning"
          }
        >
          <span>
            {describeOutcome(outcome.outcome, outcome.mode)}
            {outcome.kind === "warning" ? ` ${outcome.divergence}` : ""}
          </span>
          {(() => {
            const url = newRoomUrl(outcome.outcome, outcome.mode, frontendUrl);
            return url ? (
              <a
                href={url}
                target="_blank"
                rel="noreferrer"
                data-testid="restore-open-new-game"
                className="font-medium underline"
              >
                Open the new game ↗
              </a>
            ) : null;
          })()}
          {(() => {
            const note = agentNote(outcome.outcome);
            return note ? (
              <span
                data-testid="restore-agent-note"
                className="text-default-500"
              >
                {note}
              </span>
            ) : null;
          })()}
        </div>
      )}
      {outcome?.kind === "failure" && (
        <div
          role="alert"
          data-testid="restore-failure"
          className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger"
        >
          {outcome.message}
        </div>
      )}
    </div>
  );
}
