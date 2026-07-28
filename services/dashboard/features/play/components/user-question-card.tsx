"use client";

import { Button, Input, TextField } from "@heroui/react";
import { useCallback, useRef, useState } from "react";
import {
  UserQuestionPrompt,
  UserQuestionResolution,
} from "@/features/play/lib/play-session-events";
import { UserQuestionAnswerRequest } from "@/features/shared/lib/types";

export interface UserQuestionCardProps {
  /** The question as parsed from the `user_question` event. */
  question: UserQuestionPrompt;
  /** Derived from the job's durable event list, never held separately. */
  resolution: UserQuestionResolution;
  /** True once the owning job can no longer accept an answer. */
  isJobTerminal: boolean;
  /**
   * Submit an answer. Omitted where the transcript is read-only (the subagent
   * output view), which renders the question without controls.
   */
  onAnswer?: (
    questionId: string,
    body: UserQuestionAnswerRequest
  ) => Promise<void>;
}

/**
 * The transcript row for a question the model asked through `ask_user`: the
 * question text, one button per offered choice, and — only when the model
 * allowed it — a free-text field.
 *
 * SECURITY: `question`, and every choice's `label`, `value` and `description`,
 * are model-authored strings. They are rendered as plain React text children
 * only. Nothing here may pass them to a markdown renderer, to
 * `dangerouslySetInnerHTML`, or into an attribute the browser resolves
 * (`href`, `src`, `style`, `on*`), and choice keys are index-based because two
 * choices may share a `value`.
 */
export function UserQuestionCard({
  question,
  resolution,
  isJobTerminal,
  onAnswer,
}: UserQuestionCardProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [freeText, setFreeText] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  // The state flag drives the disabled styling, but a ref is what actually
  // makes a double-click a single answer: two clicks dispatched before React
  // re-renders would both read the stale state.
  const inFlightRef = useRef(false);

  const isPending = resolution.status === "pending";
  // A failed submit is never retried. The answer may well have landed, and
  // re-sending would either double-answer or 409 again.
  const isAnswerable =
    isPending && !isJobTerminal && onAnswer !== undefined && !submitError;
  const controlsDisabled = !isAnswerable || isSubmitting;

  const submit = useCallback(
    async (body: UserQuestionAnswerRequest) => {
      if (!onAnswer || inFlightRef.current) {
        return;
      }
      inFlightRef.current = true;
      setIsSubmitting(true);
      try {
        await onAnswer(question.questionId, body);
      } catch (error) {
        setSubmitError(
          error instanceof Error ? error.message : "Failed to send the answer"
        );
      } finally {
        inFlightRef.current = false;
        setIsSubmitting(false);
      }
    },
    [onAnswer, question.questionId]
  );

  const pendingNotice = isJobTerminal
    ? "This run has finished, so the question can no longer be answered."
    : onAnswer === undefined
      ? "This view is read-only, so the question cannot be answered here."
      : null;

  const recordedAnswer =
    resolution.status === "answered"
      ? ((resolution.source === "free_text"
          ? resolution.text
          : (resolution.label ?? resolution.value)) ?? "")
      : "";

  return (
    <div
      data-testid="user-question-card"
      className="overflow-hidden rounded-lg border border-default-200/60 bg-default-50/40 dark:bg-white/3"
    >
      <div className="flex items-center gap-2 px-3 py-2">
        <span
          aria-hidden="true"
          className={`h-1.5 w-1.5 shrink-0 rounded-full ${
            isAnswerable ? "animate-pulse bg-primary" : "bg-primary/60"
          }`}
        />
        <span className="text-xs font-medium text-default-500">
          Question for you
        </span>
      </div>

      <div className="space-y-2.5 border-t border-default-200/60 px-3 py-2.5">
        <p
          data-testid="user-question-text"
          className="max-h-60 overflow-y-auto whitespace-pre-wrap break-words text-sm leading-relaxed text-foreground"
        >
          {question.question}
        </p>

        {isPending ? (
          <>
            {question.choices.length > 0 && (
              <div
                data-testid="user-question-choices"
                className="flex flex-wrap gap-2"
              >
                {question.choices.map((choice, index) => (
                  // Index-keyed on purpose: `value` is model-authored and may
                  // repeat across choices.
                  <Button
                    key={`${question.questionId}-${index}`}
                    data-testid={`user-question-choice-${index}`}
                    isDisabled={controlsDisabled}
                    size="sm"
                    variant="ghost"
                    onPress={() => void submit({ choice_value: choice.value })}
                  >
                    <span className="flex min-w-0 flex-col items-start text-left">
                      <span className="line-clamp-2 break-words">
                        {choice.label}
                      </span>
                      {choice.description ? (
                        <span className="line-clamp-2 break-words text-[11px] font-normal text-default-400">
                          {choice.description}
                        </span>
                      ) : null}
                    </span>
                  </Button>
                ))}
              </div>
            )}

            {question.allowFreeText && (
              <div className="flex flex-wrap items-center gap-2">
                <TextField
                  fullWidth
                  aria-label="Your answer"
                  className="min-w-40 flex-1"
                  isDisabled={controlsDisabled}
                >
                  <Input
                    data-testid="user-question-free-text"
                    placeholder="Type an answer..."
                    value={freeText}
                    onChange={(event) => setFreeText(event.target.value)}
                  />
                </TextField>
                <Button
                  data-testid="user-question-free-text-submit"
                  isDisabled={controlsDisabled || freeText.trim() === ""}
                  size="sm"
                  variant="primary"
                  onPress={() => void submit({ text: freeText.trim() })}
                >
                  Send
                </Button>
              </div>
            )}

            {isSubmitting && (
              <p className="text-xs text-default-400">Sending your answer...</p>
            )}

            {pendingNotice && (
              <p
                data-testid="user-question-unanswerable"
                className="text-xs text-default-400"
              >
                {pendingNotice}
              </p>
            )}
          </>
        ) : resolution.status === "answered" ? (
          <p
            data-testid="user-question-answer"
            className="text-xs text-default-500"
          >
            {recordedAnswer ? (
              <>
                Answered:{" "}
                <span className="break-words font-medium text-foreground">
                  {recordedAnswer}
                </span>
              </>
            ) : (
              "Answered"
            )}
          </p>
        ) : (
          <p
            data-testid="user-question-closed"
            className="text-xs italic text-default-400"
          >
            {resolution.reason === "timeout"
              ? "Timed out — this question is no longer awaiting an answer."
              : "Cancelled — this question is no longer awaiting an answer."}
          </p>
        )}

        {submitError && (
          <p
            data-testid="user-question-error"
            role="status"
            className="break-words text-xs text-danger/80"
          >
            {submitError}
          </p>
        )}
      </div>
    </div>
  );
}
