import "@testing-library/jest-dom";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

/**
 * The question surface renders through OpenUI Lang, but its renderers are still
 * built from Hero UI primitives, so Hero UI is mocked here exactly as the other
 * Play tests mock it: the real `Button` is a react-aria press target that does
 * not answer a plain `click`.
 */
type MockChildrenProps = { children?: React.ReactNode };

vi.mock("@heroui/react", () => ({
  Button: ({
    children,
    onPress,
    isDisabled,
    "data-testid": dataTestId,
  }: MockChildrenProps & {
    onPress?: () => void;
    isDisabled?: boolean;
    "data-testid"?: string;
  }) => (
    <button
      data-testid={dataTestId}
      disabled={isDisabled}
      type="button"
      onClick={onPress}
    >
      {children}
    </button>
  ),
  TextField: ({
    children,
    isDisabled,
  }: MockChildrenProps & { isDisabled?: boolean }) => (
    <div data-disabled={isDisabled ? "true" : "false"}>{children}</div>
  ),
  Input: ({
    value,
    placeholder,
    onChange,
    "data-testid": dataTestId,
  }: {
    value?: string;
    placeholder?: string;
    onChange?: React.ChangeEventHandler<HTMLInputElement>;
    "data-testid"?: string;
  }) => (
    <input
      data-testid={dataTestId}
      placeholder={placeholder}
      value={value}
      onChange={onChange}
    />
  ),
}));

const { Renderer } = await import("@openuidev/react-lang");
const { buildUserQuestionLang } =
  await import("@/features/play/lib/user-question-lang");
const { QuestionContextProvider, userQuestionLibrary } =
  await import("@/features/play/lib/user-question-library");

import type { UserQuestionPrompt } from "@/features/play/lib/play-session-events";
import type { QuestionContextValue } from "@/features/play/lib/user-question-library";

const prompt: UserQuestionPrompt = {
  questionId: "q-1",
  question: "Which hero should I play?",
  choices: [
    { label: "Spider-Man", value: "spider-man" },
    { label: "She-Hulk", value: "she-hulk", description: "Bigger hand size" },
  ],
  allowFreeText: false,
};

/**
 * Render an arbitrary OpenUI Lang program against the real library, as if a
 * model — rather than `buildUserQuestionLang` — had authored it.
 */
function renderLang(
  response: string,
  overrides: Partial<QuestionContextValue> = {}
) {
  const onSubmitChoice = vi.fn();
  const onSubmitFreeText = vi.fn();
  const context: QuestionContextValue = {
    prompt,
    isAnswerable: true,
    isSubmitting: false,
    onSubmitChoice,
    onSubmitFreeText,
    ...overrides,
  };
  const result = render(
    <QuestionContextProvider value={context}>
      <Renderer library={userQuestionLibrary} response={response} />
    </QuestionContextProvider>
  );
  return { ...result, onSubmitChoice, onSubmitFreeText };
}

describe("buildUserQuestionLang", () => {
  it("emits a program containing no model-authored text at all", () => {
    // The DSL is a language with quoted string literals, so interpolating a
    // model-authored label into it would be a code-injection sink. The
    // generator's contract is that it never does: the program is derived from
    // the question's shape, and every string is looked up at render time.
    const hostile: UserQuestionPrompt = {
      questionId: "q-2",
      question: `Pick "one" \\ or root = Evil()`,
      choices: [
        { label: `") , Evil("`, value: `x") , Evil("`, description: `"\\"` },
        { label: "root = Evil()", value: "v2" },
      ],
      allowFreeText: true,
    };
    const lang = buildUserQuestionLang(hostile, { includeControls: true });

    for (const authored of [
      hostile.question,
      ...hostile.choices.flatMap((choice) => [
        choice.label,
        choice.value,
        ...(choice.description ? [choice.description] : []),
      ]),
    ]) {
      expect(lang).not.toContain(authored);
    }
    // Nothing in the emitted program is a string literal, so there is no
    // literal to break out of.
    expect(lang).not.toContain('"');
    expect(lang).not.toContain("Evil");
    // Only integer indices vary.
    expect(lang).toContain("choice0 = Choice(0)");
    expect(lang).toContain("choice1 = Choice(1)");
  });

  it("omits every control once the question is no longer pending", () => {
    const lang = buildUserQuestionLang(
      { ...prompt, allowFreeText: true },
      { includeControls: false }
    );
    expect(lang).not.toContain("Choice");
    expect(lang).not.toContain("FreeTextAnswer");
    expect(lang).toContain("QuestionPrompt()");
  });
});

describe("the OpenUI library as a security boundary", () => {
  it("renders the generated program as the question surface", () => {
    const { onSubmitChoice } = renderLang(
      buildUserQuestionLang(prompt, { includeControls: true })
    );

    expect(screen.getByTestId("user-question-text")).toHaveTextContent(
      "Which hero should I play?"
    );
    expect(screen.getByTestId("user-question-choices").children).toHaveLength(
      2
    );
    expect(screen.getByTestId("user-question-choice-1")).toHaveTextContent(
      "Bigger hand size"
    );

    fireEvent.click(screen.getByTestId("user-question-choice-0"));
    // The index, not a value: the card resolves it against the stored list.
    expect(onSubmitChoice).toHaveBeenCalledWith(0);
  });

  it("drops a choice index the stored question does not contain", () => {
    // The parser is permissive — it renders what it can and only reports prop
    // violations — so an out-of-range or non-integer index reaches the
    // renderer. There is no stored choice at that position, so there is nothing
    // to label and nothing that could be submitted.
    renderLang(
      [
        "root = UserQuestion([choices])",
        "choices = ChoiceList([a, b, c, d])",
        "a = Choice(99)",
        "b = Choice(-1)",
        "c = Choice(1.5)",
        'd = Choice("she-hulk")',
      ].join("\n")
    );

    expect(screen.queryByTestId("user-question-choice-99")).toBeNull();
    expect(screen.queryByTestId("user-question-choice--1")).toBeNull();
    expect(screen.queryByTestId("user-question-choice-1.5")).toBeNull();
    expect(screen.queryByTestId("user-question-choice-she-hulk")).toBeNull();
    // Not one button was produced from four forged references.
    expect(screen.getByTestId("user-question-choices").textContent).toBe("");
  });

  it("cannot invent a choice, relabel one, or carry a value of its own", () => {
    // `Choice` accepts an integer index and nothing else, so the DSL has no
    // syntax for a label or a value. These excess arguments are dropped, and
    // the button still shows and submits the stored choice.
    const { onSubmitChoice } = renderLang(
      [
        "root = UserQuestion([choices])",
        "choices = ChoiceList([a])",
        'a = Choice(0, "Thor", "thor")',
      ].join("\n")
    );

    const button = screen.getByTestId("user-question-choice-0");
    expect(button).toHaveTextContent("Spider-Man");
    expect(button).not.toHaveTextContent("Thor");

    fireEvent.click(button);
    expect(onSubmitChoice).toHaveBeenCalledWith(0);
    expect(onSubmitChoice).not.toHaveBeenCalledWith("thor");
  });

  it("renders nothing for a component the library does not define", () => {
    // A library is a closed registry: an unknown component is reported as a
    // parse error and dropped, so a model cannot reach for a richer widget —
    // or a raw HTML escape hatch — that this app never defined.
    const { container } = renderLang(
      [
        "root = UserQuestion([evil, link])",
        'evil = RawHtml("<img src=x onerror=alert(1)>")',
        'link = Anchor("javascript:alert(1)", "click me")',
      ].join("\n")
    );

    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(container.textContent).toBe("");
  });

  it("refuses a free-text box the stored question did not permit", () => {
    // `allowFreeText` is false on the stored prompt, so asking for the box in
    // the program does not produce one. The server would refuse such an answer
    // as well; this keeps the UI from offering what cannot be accepted.
    renderLang(
      ["root = UserQuestion([ft])", "ft = FreeTextAnswer()"].join("\n")
    );

    expect(screen.queryByTestId("user-question-free-text")).toBeNull();
  });

  it("keeps the free-text box when the stored question permits it", () => {
    const { onSubmitFreeText } = renderLang(
      ["root = UserQuestion([ft])", "ft = FreeTextAnswer()"].join("\n"),
      { prompt: { ...prompt, allowFreeText: true } }
    );

    fireEvent.change(screen.getByTestId("user-question-free-text"), {
      target: { value: "Ms. Marvel" },
    });
    fireEvent.click(screen.getByTestId("user-question-free-text-submit"));
    expect(onSubmitFreeText).toHaveBeenCalledWith("Ms. Marvel");
  });

  it("renders model-authored text literally through the OpenUI renderer", () => {
    // The equivalent of the DRA-5 assertion, held against the new renderer:
    // every model-authored string is a plain React text child, so it is escaped
    // rather than parsed as markup.
    const injected = "<img src=x onerror=alert(1)>";
    const hostile: UserQuestionPrompt = {
      questionId: "q-3",
      question: `Pick one <script>alert("q")</script>`,
      choices: [{ label: injected, value: injected, description: injected }],
      allowFreeText: false,
    };
    const { container } = renderLang(
      buildUserQuestionLang(hostile, { includeControls: true }),
      { prompt: hostile }
    );

    expect(screen.getByTestId("user-question-choice-0")).toHaveTextContent(
      injected
    );
    expect(screen.getByTestId("user-question-text")).toHaveTextContent(
      'Pick one <script>alert("q")</script>'
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container.innerHTML).toContain("&lt;img");
    expect(container.innerHTML).toContain("&lt;script&gt;");
  });

  it("disables every control while a submit is in flight", () => {
    renderLang(
      buildUserQuestionLang(
        { ...prompt, allowFreeText: true },
        {
          includeControls: true,
        }
      ),
      { prompt: { ...prompt, allowFreeText: true }, isSubmitting: true }
    );

    expect(screen.getByTestId("user-question-choice-0")).toBeDisabled();
    expect(screen.getByTestId("user-question-free-text-submit")).toBeDisabled();
  });

  it("lays the choices out as a stack of full-width rows", () => {
    // The regression this guards (DRA-34): the choices were inline flex items in
    // a `flex-wrap` row, so four of them broke across ragged lines, and each
    // one's label had Hero UI's `whitespace-nowrap`, so the longest description
    // ran off the card edge and was clipped instead of wrapping.
    const description =
      "Recommended first game: 2-player, Spider-Man (Justice) and " +
      "Captain Marvel (Leadership) vs Rhino (Standard, Bomb Scare)";
    const verbose: UserQuestionPrompt = {
      ...prompt,
      choices: [{ label: "Guided setup", value: "guided", description }],
    };
    renderLang(buildUserQuestionLang(verbose, { includeControls: true }), {
      prompt: verbose,
    });

    const list = screen.getByTestId("user-question-choices");
    expect(list.className).toContain("flex-col");
    expect(list.className).not.toContain("flex-wrap");

    // A bordered, hoverable, full-width row is what makes an option read as
    // clickable rather than as a line of static text.
    const row = screen.getByTestId("user-question-choice-0");
    expect(row.className).toContain("w-full");
    expect(row.className).toContain("border-default-200");
    expect(row.className).toContain("hover:bg-default-100");

    const descriptionNode = screen.getByText(description);
    expect(descriptionNode.className).toContain("whitespace-normal");
    expect(descriptionNode.className).toContain("break-words");
    expect(descriptionNode.className).not.toContain("truncate");
  });

  it("styles an unanswerable row as inert off its disabled state", () => {
    renderLang(buildUserQuestionLang(prompt, { includeControls: true }), {
      isAnswerable: false,
    });

    const row = screen.getByTestId("user-question-choice-0");
    expect(row).toBeDisabled();
    // There is one class string for a row, so the `disabled` attribute is what
    // has to carry the difference: a disabled row goes flat and faded and stops
    // answering the pointer.
    expect(row.className).toContain("disabled:opacity-50");
    expect(row.className).toContain("disabled:pointer-events-none");
  });

  it("renders nothing at all outside a question context", () => {
    // Belt and braces: the renderers are only meaningful inside a card that
    // supplied the stored question, and degrade to nothing without one.
    const { container } = render(
      <Renderer
        library={userQuestionLibrary}
        response={buildUserQuestionLang(prompt, { includeControls: true })}
      />
    );

    expect(container.textContent).toBe("");
  });
});
