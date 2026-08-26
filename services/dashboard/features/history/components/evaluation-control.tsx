"use client";

import {
  Alert,
  Button,
  Checkbox,
  CheckboxGroup,
  Chip,
  Label,
  Radio,
  RadioGroup,
  Spinner,
} from "@heroui/react";
import { useEffect, useState } from "react";

import {
  EvaluationRequestBody,
  EvaluationRound,
  EvaluationScope,
  GamePlatform,
  ProviderResponse,
  SkillDefinitionResponse,
} from "@/features/shared/lib/types";
import {
  JudgeDraft,
  assembleJudgeConfig,
} from "@/features/history/lib/judge-config";
import {
  listGameRounds,
  requestEvaluation,
} from "@/features/history/lib/eval-api";
import { JudgeConfigPanel } from "@/features/history/components/judge-config";
import { TextInputField } from "@/features/shared/components/form-fields";
import { ToggleInfoRow } from "@/features/shared/components/toggle-info-row";

/**
 * What the user is evaluating. ONE question, not two.
 *
 * The panel used to ask two independent ones — a `scope` (move/round/game) and a
 * target `mode` (selected event / seq range / whole game) — which produced nine
 * combinations, several meaningless, and made "grade this round" reachable only as
 * `scope: round` + `mode: selected event`: you had to click a MOVE in the
 * transcript so the server could resolve its containing round. That is the
 * confusion DRA-10 was filed for. Each choice below now owns its own follow-up
 * input, so the combinations that carried no meaning cannot be expressed at all.
 */
type EvaluationChoice = "moves" | "rounds" | "game";

/** How the "moves" choice picks its moves. */
type MoveSource = "selected" | "range";

const CHOICE_ORDER = ["moves", "rounds", "game"] as const;

const CHOICE_SCOPE: Record<EvaluationChoice, EvaluationScope> = {
  moves: "move",
  rounds: "round",
  game: "game",
};

const CHOICE_LABEL: Record<EvaluationChoice, string> = {
  moves: "Moves",
  rounds: "Rounds",
  game: "Whole game",
};

const CHOICE_DESCRIPTION: Record<EvaluationChoice, string> = {
  moves: "One verdict per move, each judged in the context of its round.",
  rounds:
    "Grades whole rounds: every move in them, then a per-player round roll-up.",
  game: "Grades everything: every move, then per-player round and game roll-ups.",
};

export interface EvaluationControlProps {
  gameId: string | null;
  platform?: GamePlatform;
  /** The currently selected timeline seq, used by the "moves" choice only. */
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
 * Configure-and-submit-only Evaluate panel: pick what to evaluate plus the judge
 * config and submit, which enqueues the request via the eval-service. The request
 * then appears in the persistent evaluations queue, where its live progress and
 * cancellation are observed — this panel can be closed immediately without
 * interrupting or losing the running evaluation.
 */
export function EvaluationControl({
  gameId,
  platform = "dragncards",
  selectedSeq,
  onEnqueued,
  judgeDraft = null,
  onJudgeDraftChange,
  providers = [],
  skills = [],
}: EvaluationControlProps) {
  const [choice, setChoice] = useState<EvaluationChoice>("moves");
  const [moveSource, setMoveSource] = useState<MoveSource>("selected");
  const [fromSeq, setFromSeq] = useState("");
  const [toSeq, setToSeq] = useState("");
  const [selectedRounds, setSelectedRounds] = useState<string[]>([]);
  const [force, setForce] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [enqueued, setEnqueued] = useState(false);
  // The game's rounds, from the eval-service, so the round picker offers real
  // rounds instead of asking for a sequence.
  const [rounds, setRounds] = useState<EvaluationRound[]>([]);
  const [roundsLoading, setRoundsLoading] = useState(gameId !== null);
  const [roundsError, setRoundsError] = useState<string | null>(null);
  const gameKey = gameId ? `${platform}:${gameId}` : null;
  const [loadedGameKey, setLoadedGameKey] = useState<string | null>(gameKey);

  // Discard the previous game's rounds and round selection during render, the
  // same reset-on-change pattern the workspace uses for its own selection. Doing
  // it synchronously inside the effect below would cascade renders (and is
  // rejected by the repo's lint rules); doing it in the effect's async callback
  // would leave the picker briefly offering another game's rounds.
  if (gameKey !== loadedGameKey) {
    setLoadedGameKey(gameKey);
    setSelectedRounds([]);
    setRounds([]);
    setRoundsError(null);
    setRoundsLoading(gameId !== null);
  }

  useEffect(() => {
    if (!gameId) return;
    let cancelled = false;
    (platform === "marvel-lcg"
      ? listGameRounds(gameId, platform)
      : listGameRounds(gameId)
    )
      .then((loaded) => {
        if (cancelled) return;
        setRounds(loaded);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setRounds([]);
        setRoundsError(
          e instanceof Error ? e.message : "Could not load this game's rounds."
        );
      })
      .finally(() => {
        if (!cancelled) setRoundsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [gameId, platform]);

  const buildBody = (): EvaluationRequestBody | { error: string } => {
    const judge = judgeDraft ? assembleJudgeConfig(judgeDraft) : undefined;
    const scope = CHOICE_SCOPE[choice];
    const withJudge = <T extends EvaluationRequestBody>(body: T): T =>
      judge ? { ...body, judge } : body;
    const platformBody = platform === "marvel-lcg" ? { platform } : {};

    if (choice === "game") {
      // The whole game needs no further input: the transcript selection and the
      // seq range have no bearing on what is submitted.
      return withJudge({
        scope,
        selection: { whole_game: true },
        ...platformBody,
        force,
      });
    }
    if (choice === "rounds") {
      if (selectedRounds.length === 0) {
        return { error: "Pick at least one round to evaluate." };
      }
      // Rounds go out as their RAW round numbers, which is exactly what the
      // eval-service's selection accepts. No move id is involved.
      return withJudge({
        scope,
        selection: { rounds: selectedRounds.map((value) => Number(value)) },
        ...platformBody,
        force,
      });
    }
    if (moveSource === "selected") {
      if (selectedSeq === null) {
        return { error: "Select a timeline event to evaluate." };
      }
      return withJudge({
        scope,
        selection: { seqs: [selectedSeq] },
        ...platformBody,
        force,
      });
    }
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
      ...platformBody,
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
      className="flex flex-col gap-4 border-t border-default-200/60 p-4"
      data-testid="evaluation-control"
    >
      <div className="flex flex-col gap-0.5">
        <span className="text-sm font-semibold text-foreground">Evaluate</span>
        <span className="text-xs text-default-400">
          Request an LLM verdict for moves, rounds, or the whole game.
        </span>
      </div>

      <div className="grid gap-2">
        <Label className="block text-xs font-semibold uppercase tracking-wider text-default-400">
          What to evaluate
        </Label>
        <RadioGroup
          aria-label="What to evaluate"
          value={choice}
          isDisabled={disabled}
          onChange={(next) => setChoice(next as EvaluationChoice)}
          className="gap-2"
        >
          {CHOICE_ORDER.map((value) => (
            <Radio key={value} value={value} aria-label={CHOICE_LABEL[value]}>
              {/* Radio.Content is the clickable RadioButton, so the test id and
                  the click target belong on it -- not on the label wrapper. */}
              <Radio.Content
                className="flex items-start gap-2"
                data-testid={`eval-choice-${value}`}
              >
                <Radio.Control className="mt-0.5 shrink-0">
                  <Radio.Indicator />
                </Radio.Control>
                <span className="flex flex-col">
                  <span className="text-sm text-foreground">
                    {CHOICE_LABEL[value]}
                  </span>
                  <span className="text-xs text-default-400">
                    {CHOICE_DESCRIPTION[value]}
                  </span>
                </span>
              </Radio.Content>
            </Radio>
          ))}
        </RadioGroup>
      </div>

      {choice === "moves" && (
        <div className="grid gap-2 rounded-lg border border-default-200/60 p-3">
          <Label className="block text-xs font-semibold uppercase tracking-wider text-default-400">
            Which moves
          </Label>
          <RadioGroup
            aria-label="Which moves"
            value={moveSource}
            isDisabled={disabled}
            onChange={(next) => setMoveSource(next as MoveSource)}
            className="gap-2"
          >
            <Radio value="selected" aria-label="The selected timeline event">
              <Radio.Content
                className="flex items-center gap-2"
                data-testid="eval-move-source-selected"
              >
                <Radio.Control className="shrink-0">
                  <Radio.Indicator />
                </Radio.Control>
                <span className="flex items-center gap-1.5 text-sm text-foreground">
                  The selected timeline event
                  {selectedSeq !== null ? (
                    <Chip size="sm" variant="soft" color="default">
                      #{selectedSeq}
                    </Chip>
                  ) : (
                    <span className="text-xs text-default-400">
                      (none selected)
                    </span>
                  )}
                </span>
              </Radio.Content>
            </Radio>
            <Radio value="range" aria-label="A seq range">
              <Radio.Content
                className="flex items-center gap-2"
                data-testid="eval-move-source-range"
              >
                <Radio.Control className="shrink-0">
                  <Radio.Indicator />
                </Radio.Control>
                <span className="text-sm text-foreground">A seq range</span>
              </Radio.Content>
            </Radio>
          </RadioGroup>
          {moveSource === "range" && (
            <div className="grid grid-cols-2 gap-2 pl-6">
              <TextInputField
                id="eval-from-seq-field"
                label="From seq"
                placeholder="from"
                value={fromSeq}
                disabled={disabled}
                inputTestId="eval-from-seq"
                onChange={setFromSeq}
              />
              <TextInputField
                id="eval-to-seq-field"
                label="To seq"
                placeholder="to"
                value={toSeq}
                disabled={disabled}
                inputTestId="eval-to-seq"
                onChange={setToSeq}
              />
            </div>
          )}
        </div>
      )}

      {choice === "rounds" && (
        <div
          className="grid gap-2 rounded-lg border border-default-200/60 p-3"
          data-testid="eval-round-picker"
        >
          <Label className="block text-xs font-semibold uppercase tracking-wider text-default-400">
            Which rounds
          </Label>
          {roundsLoading ? (
            <span className="flex items-center gap-2 text-xs text-default-400">
              <Spinner size="sm" />
              Loading this game&apos;s rounds…
            </span>
          ) : roundsError ? (
            <Alert status="warning" data-testid="eval-rounds-error">
              <Alert.Content>
                <Alert.Description>{roundsError}</Alert.Description>
              </Alert.Content>
            </Alert>
          ) : rounds.length === 0 ? (
            <p
              data-testid="eval-rounds-empty"
              className="text-xs text-default-400"
            >
              No round has closed in this game yet, so there is nothing to grade
              at round level. Evaluate moves or the whole game instead.
            </p>
          ) : (
            <CheckboxGroup
              aria-label="Which rounds"
              value={selectedRounds}
              isDisabled={disabled}
              onChange={setSelectedRounds}
              className="gap-1.5"
            >
              {rounds.map((round) => (
                <Checkbox
                  key={round.round_number}
                  value={String(round.round_number)}
                  aria-label={round.label}
                >
                  <Checkbox.Content
                    className="flex items-center gap-2"
                    data-testid={`eval-round-${round.round_number}`}
                  >
                    <Checkbox.Control className="shrink-0">
                      <Checkbox.Indicator />
                    </Checkbox.Control>
                    <span className="text-sm text-foreground">
                      {round.label}
                      <span className="ml-1.5 text-xs text-default-400">
                        {round.move_count} move
                        {round.move_count === 1 ? "" : "s"} · #{round.from_seq}
                        –#{round.to_seq}
                      </span>
                    </span>
                  </Checkbox.Content>
                </Checkbox>
              ))}
            </CheckboxGroup>
          )}
        </div>
      )}

      <ToggleInfoRow
        label="Re-evaluate"
        description="Grade again even if a verdict already exists."
        checked={force}
        disabled={disabled}
        testId="eval-force"
        onChange={setForce}
      />

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
          <Alert.Content>
            <Alert.Description>{error}</Alert.Description>
          </Alert.Content>
        </Alert>
      )}

      {enqueued && (
        <Alert status="success" role="status" data-testid="eval-enqueued">
          <Alert.Content>
            <Alert.Description>
              Added to the queue. Track its progress and cancel it from the
              Evaluations queue — you can close this panel.
            </Alert.Description>
          </Alert.Content>
        </Alert>
      )}
    </div>
  );
}
