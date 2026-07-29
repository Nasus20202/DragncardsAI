"use client";

import { Button, Input, TextField } from "@heroui/react";
import {
  ComponentRenderer,
  createLibrary,
  defineComponent,
} from "@openuidev/react-lang";
import { createContext, Fragment, useContext, useState } from "react";
import { z } from "zod";
import { UserQuestionPrompt } from "@/features/play/lib/play-session-events";

/**
 * The OpenUI Lang component library the question surface renders through.
 *
 * SECURITY MODEL
 * ==============
 * A library passed to OpenUI's `Renderer` is a closed registry: a program
 * naming a component that is not defined here renders nothing and is reported
 * as an `unknown-component` parse error. So this file is the complete list of
 * what any OpenUI Lang program can put on screen for a question.
 *
 * Two properties are load-bearing, and both are enforced here rather than by
 * the library:
 *
 *  1. **A prop schema is not a runtime guard.** `@openuidev/lang-core` 0.2.10
 *     uses the zod schemas below to generate the model's prompt and to report
 *     validation errors, but it renders permissively: a program written as
 *     `Choice("not-a-number")` reaches the renderer with `index` still set to
 *     the string. Every renderer below therefore re-checks its own props
 *     against the stored question and renders nothing when they do not hold.
 *
 *  2. **Presentation comes from the DSL; data comes from the row.** Nothing a
 *     program says can widen what may be answered. A `Choice` carries an
 *     integer index and nothing else; its label, description and — critically —
 *     its submitted `value` are read from `QuestionContext`, which holds the
 *     prompt as parsed from the durable `user_question` event. A free-text box
 *     renders only when the *stored* `allowFreeText` is true, whatever the
 *     program asked for.
 *
 * Every string these renderers display is model-authored and is passed as a
 * plain React text child. No renderer here may introduce
 * `dangerouslySetInnerHTML`, a markdown renderer, or a browser-resolved
 * attribute (`href`, `src`, `style`, `on*`).
 *
 * The components deliberately use the same Hero UI primitives and Tailwind
 * theme tokens the transcript already used, so adopting OpenUI changed the
 * rendering pipeline without changing a pixel.
 */

export interface QuestionContextValue {
  /** The question as parsed from the durable event — the only authority. */
  prompt: UserQuestionPrompt;
  /** False once the question can no longer be answered, for any reason. */
  isAnswerable: boolean;
  /** True while a submit is in flight. */
  isSubmitting: boolean;
  /** Submit the choice stored at `index`, or free text. */
  onSubmitChoice: (index: number) => void;
  onSubmitFreeText: (text: string) => void;
}

const QuestionContext = createContext<QuestionContextValue | null>(null);

export const QuestionContextProvider = QuestionContext.Provider;

function useQuestionContext(): QuestionContextValue | null {
  return useContext(QuestionContext);
}

/**
 * One offered choice, addressed only by its position in the stored list.
 *
 * `index` is the entire prop surface on purpose. The label shown and the value
 * submitted are both read from the stored prompt, so a program can reorder or
 * omit choices (presentation) but can neither relabel one nor invent one.
 */
const ChoiceView: ComponentRenderer<{ index: number }> = ({ props }) => {
  const context = useQuestionContext();
  // Re-checked rather than trusted: see property (1) in the file comment.
  // A non-integer, negative or out-of-range index addresses no stored choice,
  // so there is nothing to render and nothing that could be submitted.
  if (
    !context ||
    !Number.isInteger(props.index) ||
    props.index < 0 ||
    props.index >= context.prompt.choices.length
  ) {
    return null;
  }
  const index = props.index;
  const choice = context.prompt.choices[index];
  const disabled = !context.isAnswerable || context.isSubmitting;

  return (
    <Button
      data-testid={`user-question-choice-${index}`}
      isDisabled={disabled}
      size="sm"
      variant="ghost"
      onPress={() => context.onSubmitChoice(index)}
    >
      <span className="flex min-w-0 flex-col items-start text-left">
        <span className="line-clamp-2 break-words">{choice.label}</span>
        {choice.description ? (
          <span className="line-clamp-2 break-words text-[11px] font-normal text-default-400">
            {choice.description}
          </span>
        ) : null}
      </span>
    </Button>
  );
};

const Choice = defineComponent({
  name: "Choice",
  description:
    "One answer the user can click. Identified only by its zero-based index " +
    "into the question's stored choice list; its label and submitted value " +
    "come from that list.",
  props: z.object({
    index: z
      .number()
      .int()
      .describe("Zero-based index into the question's stored choice list"),
  }),
  component: ChoiceView,
});

/** The row of choice buttons. */
const ChoiceList = defineComponent({
  name: "ChoiceList",
  description: "A wrapping row of the choices the user can click.",
  props: z.object({
    choices: z
      .array(Choice.ref)
      .optional()
      .describe("The choices to lay out, in display order"),
  }),
  component: ({ props, renderNode }) => {
    const choices = props.choices ?? [];
    if (choices.length === 0) {
      return null;
    }
    return (
      <div data-testid="user-question-choices" className="flex flex-wrap gap-2">
        {choices.map((choice, index) => (
          // Index-keyed on purpose: nothing in a choice is unique. Two stored
          // choices may share a value, and a program may repeat an index.
          // A Fragment rather than a wrapper element: `gap-2` spaces flex
          // items, and a wrapper would become the flex item instead of the
          // button.
          <Fragment key={index}>{renderNode(choice)}</Fragment>
        ))}
      </div>
    );
  },
});

const QuestionPromptView: ComponentRenderer<Record<never, never>> = () => {
  const context = useQuestionContext();
  if (!context) {
    return null;
  }
  return (
    <p
      data-testid="user-question-text"
      className="max-h-60 overflow-y-auto whitespace-pre-wrap break-words text-sm leading-relaxed text-foreground"
    >
      {context.prompt.question}
    </p>
  );
};

/** The question text itself, read from the stored prompt. */
const QuestionPrompt = defineComponent({
  name: "QuestionPrompt",
  description:
    "The text of the question. Takes no arguments: the wording is the " +
    "question as it was stored and cannot be restated.",
  props: z.object({}),
  component: QuestionPromptView,
});

/**
 * The free-text box, shown only when the stored question permits free text.
 *
 * A program that asks for this box on a question whose stored `allow_free_text`
 * is false gets nothing — and the server would refuse such an answer anyway.
 */
const FreeTextAnswerView: ComponentRenderer<Record<never, never>> = () => {
  const context = useQuestionContext();
  const [text, setText] = useState("");
  if (!context || !context.prompt.allowFreeText) {
    return null;
  }
  const disabled = !context.isAnswerable || context.isSubmitting;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <TextField
        fullWidth
        aria-label="Your answer"
        className="min-w-40 flex-1"
        isDisabled={disabled}
      >
        <Input
          data-testid="user-question-free-text"
          placeholder="Type an answer..."
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
      </TextField>
      <Button
        data-testid="user-question-free-text-submit"
        isDisabled={disabled || text.trim() === ""}
        size="sm"
        variant="primary"
        onPress={() => context.onSubmitFreeText(text.trim())}
      >
        Send
      </Button>
    </div>
  );
};

const FreeTextAnswer = defineComponent({
  name: "FreeTextAnswer",
  description:
    "A box for typing an answer. Renders only when the stored question " +
    "permits a free-text answer.",
  props: z.object({}),
  component: FreeTextAnswerView,
});

/** The root: stacks the question text above whatever controls are offered. */
const UserQuestion = defineComponent({
  name: "UserQuestion",
  description: "The question surface. The root component of every question.",
  props: z.object({
    children: z
      .array(z.any())
      .optional()
      .describe("The question text, then the controls, in display order"),
  }),
  component: ({ props, renderNode }) => (
    <div className="space-y-2.5">
      {(props.children ?? []).map((child, index) => (
        // A Fragment rather than a wrapper element, so the question text and
        // the controls stay the direct children of `space-y-2.5`. Tailwind
        // spaces siblings with `margin-top`, and a `display: contents` wrapper
        // would swallow it and collapse the gaps.
        <Fragment key={index}>{renderNode(child)}</Fragment>
      ))}
    </div>
  ),
});

export const userQuestionLibrary = createLibrary({
  components: [
    UserQuestion,
    QuestionPrompt,
    ChoiceList,
    Choice,
    FreeTextAnswer,
  ],
  root: "UserQuestion",
});
