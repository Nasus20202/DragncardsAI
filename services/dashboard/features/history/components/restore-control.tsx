"use client";

import { Button, Chip, Spinner } from "@heroui/react";
import { useState } from "react";

import { RestoreMode, RestoreOutcome } from "@/features/shared/lib/types";

export interface RestoreControlProps {
  targetSeq: number | null;
  onRestore: (targetSeq: number, mode: RestoreMode) => Promise<RestoreOutcome>;
}

type Outcome =
  | { kind: "success"; outcome: RestoreOutcome }
  | { kind: "warning"; outcome: RestoreOutcome; divergence: string }
  | { kind: "failure"; message: string }
  | null;

function describeOutcome(outcome: RestoreOutcome): string {
  if (typeof outcome.message === "string" && outcome.message.length > 0) {
    return outcome.message;
  }
  if (typeof outcome.session_id === "string" && outcome.session_id.length > 0) {
    return `Restored into session ${outcome.session_id}.`;
  }
  return "Restore completed.";
}

export function RestoreControl({ targetSeq, onRestore }: RestoreControlProps) {
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
            divergence:
              divergence ?? "Restore could not be verified against the target.",
          });
        } else {
          setOutcome({ kind: "success", outcome: result });
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
        <span className="text-sm font-semibold text-foreground">Restore</span>
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
            <span className="font-medium text-foreground">
              New branchable session
            </span>
            <span className="block text-xs text-default-400">
              Leaves the original timeline untouched.
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
            <span className="font-medium text-foreground">
              In-place overwrite
            </span>
            <span className="block text-xs text-default-400">
              Rewinds the live session to this moment.
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
        {isRestoring ? (
          <Spinner size="sm" />
        ) : needsConfirm ? (
          "Confirm overwrite"
        ) : (
          "Restore"
        )}
      </Button>

      {outcome?.kind === "success" && (
        <div
          role="status"
          data-testid="restore-success"
          className="rounded-lg border border-success/30 bg-success/10 px-3 py-2 text-xs text-success"
        >
          {describeOutcome(outcome.outcome)}
        </div>
      )}
      {outcome?.kind === "warning" && (
        <div
          role="status"
          data-testid="restore-warning"
          className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning"
        >
          {describeOutcome(outcome.outcome)} {outcome.divergence}
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
