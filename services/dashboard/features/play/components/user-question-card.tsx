"use client";

import { Renderer } from "@openuidev/react-lang";
import { useCallback, useMemo, useRef, useState } from "react";
import {
  UserQuestionPrompt,
  UserQuestionResolution,
} from "@/features/play/lib/play-session-events";
import { buildUserQuestionLang } from "@/features/play/lib/user-question-lang";
import {
  QuestionContextProvider,
  QuestionContextValue,
  userQuestionLibrary,
} from "@/features/play/lib/user-question-library";
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
 * The surface inside the card frame is rendered by OpenUI Lang
 * (`@openuidev/react-lang`) against the closed component library in
 * `features/play/lib/user-question-library.tsx`.
 *
 * SECURITY: nothing about adopting OpenUI moved the boundary. The submitted
 * answer is still `choice_value` taken from the stored choice list, and the
 * server still checks it against `choices_json` read back from the row, so a
 * forged value is refused there regardless of what was rendered. On this side:
 *
 *  - The Lang program is built by `buildUserQuestionLang` from the stored
 *    question's *shape* only, so no model-authored string is ever interpolated
 *    into DSL source.
 *  - A choice is addressed by its index into `question.choices`, so the value
 *    submitted below comes from this component's own props — never from the
 *    rendered program.
 *  - Every model-authored string is rendered as a plain React text child by the
 *    library's renderers. None reaches `dangerouslySetInnerHTML`, a markdown
 *    renderer, or a browser-resolved attribute.
 */
export function UserQuestionCard({
  question,
  resolution,
  isJobTerminal,
  onAnswer,
}: UserQuestionCardProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
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

  // Controls are only ever emitted into the program while the question is
  // answerable, so a resolved question renders its wording and nothing more.
  const lang = useMemo(
    () => buildUserQuestionLang(question, { includeControls: isPending }),
    [question, isPending]
  );

  const context = useMemo<QuestionContextValue>(
    () => ({
      prompt: question,
      isAnswerable,
      isSubmitting,
      // The index is resolved against this component's own `question` prop, so
      // the value sent is the stored one whatever the program rendered.
      onSubmitChoice: (index) => {
        const choice = question.choices[index];
        if (!choice) {
          return;
        }
        void submit({ choice_value: choice.value });
      },
      onSubmitFreeText: (text) => {
        if (!question.allowFreeText || text === "") {
          return;
        }
        void submit({ text });
      },
    }),
    [question, isAnswerable, isSubmitting, submit]
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
        <QuestionContextProvider value={context}>
          <Renderer library={userQuestionLibrary} response={lang} />
        </QuestionContextProvider>

        {isPending ? (
          <>
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
