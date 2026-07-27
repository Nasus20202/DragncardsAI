"use client";

import { Alert, Button, Chip, Radio, RadioGroup, Spinner } from "@heroui/react";
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

      <RadioGroup
        aria-label="Restore target mode"
        className="flex flex-col gap-2"
        value={mode}
        isDisabled={disabled}
        onChange={(next) => setMode(next as RestoreMode)}
      >
        <Radio value="new">
          <Radio.Content className="flex items-start gap-2 text-sm">
            <Radio.Control className="mt-1">
              <Radio.Indicator />
            </Radio.Control>
            <span>
              <span className="font-medium text-foreground">
                New branchable session
              </span>
              <span className="block text-xs text-default-400">
                Leaves the original timeline untouched.
              </span>
            </span>
          </Radio.Content>
        </Radio>
        <Radio value="in_place">
          <Radio.Content className="flex items-start gap-2 text-sm">
            <Radio.Control className="mt-1">
              <Radio.Indicator />
            </Radio.Control>
            <span>
              <span className="font-medium text-foreground">
                In-place overwrite
              </span>
              <span className="block text-xs text-default-400">
                Rewinds the live session to this moment.
              </span>
            </span>
          </Radio.Content>
        </Radio>
      </RadioGroup>

      {mode === "in_place" && (
        <Alert
          status="danger"
          role="alert"
          data-testid="restore-in-place-warning"
        >
          Warning: game state recorded after the selected moment will be
          discarded. This cannot be undone.
        </Alert>
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
        <Alert status="success" role="status" data-testid="restore-success">
          {describeOutcome(outcome.outcome)}
        </Alert>
      )}
      {outcome?.kind === "warning" && (
        <Alert status="warning" role="status" data-testid="restore-warning">
          {describeOutcome(outcome.outcome)} {outcome.divergence}
        </Alert>
      )}
      {outcome?.kind === "failure" && (
        <Alert status="danger" role="alert" data-testid="restore-failure">
          {outcome.message}
        </Alert>
      )}
    </div>
  );
}
