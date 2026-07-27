"use client";

import {
  Alert,
  Button,
  Checkbox,
  Chip,
  Input,
  Radio,
  RadioGroup,
  Spinner,
  TextField,
} from "@heroui/react";
import { useState } from "react";

import {
  EvaluationRequestBody,
  EvaluationScope,
  ProviderResponse,
  SkillDefinitionResponse,
} from "@/features/shared/lib/types";
import {
  JudgeDraft,
  assembleJudgeConfig,
} from "@/features/history/lib/judge-config";
import { requestEvaluation } from "@/features/history/lib/eval-api";
import { JudgeConfigPanel } from "@/features/history/components/judge-config";

type SelectionMode = "selected" | "range" | "whole_game";

export interface EvaluationControlProps {
  gameId: string | null;
  /** The currently selected timeline seq, used for the "selected" mode. */
  selectedSeq: number | null;
  /**
   * Called after a request is successfully enqueued so the workspace can
   * refresh the persistent queue (and optionally open it). Progress, judge
   * output, and cancellation are now observed in the queue, not here.
   */
  onEnqueued?: () => void;
  /**
   * Judge configuration draft + the provider/skill sources to populate the
   * config panel. When omitted, the judge panel is hidden and requests carry
   * no `judge` object (the server applies its defaults).
   */
  judgeDraft?: JudgeDraft | null;
  onJudgeDraftChange?: (next: JudgeDraft) => void;
  providers?: ProviderResponse[];
  skills?: SkillDefinitionResponse[];
}

/**
 * Configure-and-submit-only Evaluate panel: pick scope + judge config and
 * submit, which enqueues the request via the eval-service. The request then
 * appears in the persistent evaluations queue, where its live progress and
 * cancellation are observed — this panel can be closed immediately without
 * interrupting or losing the running evaluation.
 */
export function EvaluationControl({
  gameId,
  selectedSeq,
  onEnqueued,
  judgeDraft = null,
  onJudgeDraftChange,
  providers = [],
  skills = [],
}: EvaluationControlProps) {
  const [scope, setScope] = useState<EvaluationScope>("move");
  const [mode, setMode] = useState<SelectionMode>("selected");
  const [fromSeq, setFromSeq] = useState("");
  const [toSeq, setToSeq] = useState("");
  const [force, setForce] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [enqueued, setEnqueued] = useState(false);

  const buildBody = (): EvaluationRequestBody | { error: string } => {
    const judge = judgeDraft ? assembleJudgeConfig(judgeDraft) : undefined;
    const withJudge = <T extends EvaluationRequestBody>(body: T): T =>
      judge ? { ...body, judge } : body;

    if (mode === "whole_game") {
      return withJudge({ scope, selection: { whole_game: true }, force });
    }
    if (mode === "selected") {
      if (selectedSeq === null) {
        return { error: "Select a timeline event to evaluate." };
      }
      return withJudge({ scope, selection: { seqs: [selectedSeq] }, force });
    }
    // range
    const from = Number.parseInt(fromSeq, 10);
    const to = Number.parseInt(toSeq, 10);
    if (Number.isNaN(from) || Number.isNaN(to)) {
      return { error: "Enter a numeric from/to seq range." };
    }
    if (from > to) {
      return { error: "Range start must not exceed range end." };
    }
    return withJudge({
      scope,
      selection: { seq_range: { from_seq: from, to_seq: to } },
      force,
    });
  };

  const handleSubmit = async () => {
    if (!gameId) {
      setError("No game selected.");
      return;
    }
    const body = buildBody();
    if ("error" in body) {
      setError(body.error);
      return;
    }
    setError(null);
    setEnqueued(false);
    setIsSubmitting(true);
    try {
      await requestEvaluation(gameId, body);
      // The request now lives in the persistent queue; surface a brief
      // confirmation and let the workspace refresh/open the queue. The panel
      // can be closed right away without affecting the running evaluation.
      setEnqueued(true);
      onEnqueued?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Evaluation request failed.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const disabled = gameId === null || isSubmitting;

  return (
    <div
      className="flex flex-col gap-3 border-t border-default-200/60 p-4"
      data-testid="evaluation-control"
    >
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-foreground">Evaluate</span>
        <span className="text-xs text-default-400">
          Request an LLM verdict for a move, a round, or the whole game.
        </span>
      </div>

      <div className="flex flex-col gap-1">
        <span className="text-xs font-semibold uppercase tracking-wide text-default-400">
          Scope
        </span>
        <RadioGroup
          aria-label="Evaluation scope"
          className="flex flex-row flex-wrap gap-4"
          value={scope}
          isDisabled={disabled}
          onChange={(next) => {
            if (next === "game") {
              // A whole-game cascade grades the entire game; pin the target
              // selection to the whole game so the request reads cleanly.
              setScope("game");
              setMode("whole_game");
              return;
            }
            setScope(next as EvaluationScope);
          }}
        >
          <Radio value="move">
            <Radio.Content className="flex items-center gap-1.5 text-sm">
              <Radio.Control>
                <Radio.Indicator />
              </Radio.Control>
              <span>Move</span>
            </Radio.Content>
          </Radio>
          <Radio value="round">
            <Radio.Content className="flex items-center gap-1.5 text-sm">
              <Radio.Control>
                <Radio.Indicator />
              </Radio.Control>
              <span>Round</span>
            </Radio.Content>
          </Radio>
          <Radio value="game">
            <Radio.Content className="flex items-center gap-1.5 text-sm">
              <Radio.Control>
                <Radio.Indicator />
              </Radio.Control>
              <span>Whole game (cascade)</span>
            </Radio.Content>
          </Radio>
        </RadioGroup>
        {scope !== "move" && (
          <p
            data-testid="eval-cascade-note"
            className="text-xs text-default-400"
          >
            {scope === "game"
              ? "Grades the whole game: every move, then per-player round roll-ups, then per-player game roll-ups."
              : "Grades the round: every move in it, then per-player round roll-ups."}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-default-400">
          Targets
        </span>
        <RadioGroup
          aria-label="Evaluation targets"
          className="flex flex-col gap-2"
          value={mode}
          isDisabled={disabled}
          onChange={(next) => setMode(next as SelectionMode)}
        >
          <Radio value="selected">
            <Radio.Content className="flex items-center gap-1.5 text-sm">
              <Radio.Control>
                <Radio.Indicator />
              </Radio.Control>
              <span>
                Selected event
                {selectedSeq !== null ? (
                  <Chip
                    size="sm"
                    variant="soft"
                    color="default"
                    className="ml-1.5"
                  >
                    #{selectedSeq}
                  </Chip>
                ) : (
                  <span className="ml-1.5 text-xs text-default-400">
                    (none selected)
                  </span>
                )}
              </span>
            </Radio.Content>
          </Radio>
          <Radio value="range">
            <Radio.Content className="flex items-center gap-1.5 text-sm">
              <Radio.Control>
                <Radio.Indicator />
              </Radio.Control>
              <span>Seq range</span>
            </Radio.Content>
          </Radio>
          {mode === "range" && (
            <div className="flex items-center gap-2 pl-5">
              <TextField aria-label="From seq" isDisabled={disabled}>
                <Input
                  type="number"
                  aria-label="From seq"
                  data-testid="eval-from-seq"
                  className="w-20"
                  value={fromSeq}
                  onChange={(event) => setFromSeq(event.target.value)}
                  placeholder="from"
                />
              </TextField>
              <span className="text-xs text-default-400">to</span>
              <TextField aria-label="To seq" isDisabled={disabled}>
                <Input
                  type="number"
                  aria-label="To seq"
                  data-testid="eval-to-seq"
                  className="w-20"
                  value={toSeq}
                  onChange={(event) => setToSeq(event.target.value)}
                  placeholder="to"
                />
              </TextField>
            </div>
          )}
          <Radio value="whole_game">
            <Radio.Content className="flex items-center gap-1.5 text-sm">
              <Radio.Control>
                <Radio.Indicator />
              </Radio.Control>
              <span>Whole game</span>
            </Radio.Content>
          </Radio>
        </RadioGroup>
      </div>

      <Checkbox
        data-testid="eval-force"
        isSelected={force}
        isDisabled={disabled}
        onChange={setForce}
      >
        <Checkbox.Content className="flex items-center gap-1.5 text-sm">
          <Checkbox.Control>
            <Checkbox.Indicator />
          </Checkbox.Control>
          <span>Re-evaluate even if a verdict already exists</span>
        </Checkbox.Content>
      </Checkbox>

      {judgeDraft && onJudgeDraftChange && (
        <JudgeConfigPanel
          draft={judgeDraft}
          providers={providers}
          skills={skills}
          disabled={disabled}
          onChange={onJudgeDraftChange}
        />
      )}

      <Button
        type="button"
        variant="primary"
        isDisabled={disabled}
        data-testid="eval-submit"
        onPress={() => void handleSubmit()}
      >
        {isSubmitting ? <Spinner size="sm" /> : "Request evaluation"}
      </Button>

      {error && (
        <Alert status="danger" role="alert" data-testid="eval-error">
          {error}
        </Alert>
      )}

      {enqueued && (
        <Alert status="success" role="status" data-testid="eval-enqueued">
          Added to the queue. Track its progress and cancel it from the
          Evaluations queue — you can close this panel.
        </Alert>
      )}
    </div>
  );
}
