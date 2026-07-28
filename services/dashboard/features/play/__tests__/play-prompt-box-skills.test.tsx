import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { useState } from "react";

import { PlayPromptBox } from "@/features/play/components/play-prompt-box";
import {
  SessionDetail,
  SkillDefinitionResponse,
} from "@/features/shared/lib/types";

vi.mock("@/features/play/components/context-health-widget", () => ({
  ContextHealthWidget: () => null,
}));

const activeSession: SessionDetail = {
  id: "session-1",
  name: "Session",
  status: "active",
  context_recent_message_limit: null,
  context_recent_tool_exchange_limit: null,
  metadata: {},
  created_at: "2026-05-11T00:00:00Z",
  updated_at: "2026-05-11T00:00:00Z",
  terminated_at: null,
  model_config: null,
  skills: [],
  mcps: [],
  recent_job: null,
  recent_jobs: [],
};

const skills: SkillDefinitionResponse[] = [
  {
    name: "marvel-champions-play",
    path: "/skills/marvel-champions-play",
    description: "Play Marvel Champions",
    metadata: {},
  },
  {
    name: "board-reader",
    path: "/skills/board-reader",
    description: "Read the board",
    metadata: {},
  },
];

type PromptBoxProps = React.ComponentProps<typeof PlayPromptBox>;

/**
 * `PlayPromptBox` is a controlled component: it reads the prompt text from its
 * props, so the harness has to own that text the way `PlayWorkspace` does.
 * Without it, a mention could never be removed from text the component cannot
 * see.
 */
function Harness({
  initialPrompt,
  onPromptChange,
  ...props
}: Omit<PromptBoxProps, "prompt"> & { initialPrompt: string }) {
  const [prompt, setPrompt] = useState(initialPrompt);
  return (
    <PlayPromptBox
      {...props}
      prompt={prompt}
      onPromptChange={(value) => {
        setPrompt(value);
        onPromptChange(value);
      }}
    />
  );
}

function renderPromptBox(
  overrides: Partial<PromptBoxProps> & { prompt?: string } = {}
) {
  const { prompt = "", ...rest } = overrides;
  const props = {
    selectedSession: activeSession,
    activeJobId: null,
    isBusy: false,
    cancelPending: false,
    contextMetadata: null,
    skills,
    attachedSkills: [] as string[],
    onPromptChange: vi.fn(),
    onSubmit: vi.fn(),
    onCancelExecution: vi.fn(),
    onCompact: vi.fn(),
    onAttachSkill: vi.fn(),
    onDetachSkill: vi.fn(),
    ...rest,
  };
  render(<Harness {...props} initialPrompt={prompt} />);
  return props;
}

/** Type into the prompt textarea, reporting the caret at the end of the text. */
function typePrompt(value: string, caret = value.length) {
  const input = screen.getByTestId("play-prompt-input");
  fireEvent.change(input, { target: { value, selectionStart: caret } });
  return input;
}

describe("PlayPromptBox skill mentions", () => {
  it("opens the skill picker when the mention trigger is typed", () => {
    renderPromptBox();

    typePrompt("@");

    expect(screen.getByTestId("skill-mention-picker")).toBeInTheDocument();
    expect(
      screen.getByTestId("skill-mention-option-marvel-champions-play")
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("skill-mention-option-board-reader")
    ).toBeInTheDocument();
  });

  it("filters the picker by the mention query", () => {
    renderPromptBox();

    typePrompt("play @board");

    expect(
      screen.getByTestId("skill-mention-option-board-reader")
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("skill-mention-option-marvel-champions-play")
    ).not.toBeInTheDocument();
  });

  it("does not open the picker for a trigger inside a word", () => {
    renderPromptBox();

    typePrompt("mail@example.com");

    expect(
      screen.queryByTestId("skill-mention-picker")
    ).not.toBeInTheDocument();
  });

  it("attaches the chosen skill and completes the mention token", () => {
    const props = renderPromptBox();

    typePrompt("play @board");
    fireEvent.click(screen.getByTestId("skill-mention-option-board-reader"));

    expect(props.onAttachSkill).toHaveBeenCalledWith("board-reader");
    expect(props.onPromptChange).toHaveBeenCalledWith("play @board-reader ");
    expect(screen.getByTestId("play-prompt-input")).toHaveValue(
      "play @board-reader "
    );
    expect(
      screen.queryByTestId("skill-mention-picker")
    ).not.toBeInTheDocument();
  });

  it("leaves the caret after the completed token", () => {
    renderPromptBox();

    typePrompt("play @board mid", 11);
    fireEvent.click(screen.getByTestId("skill-mention-option-board-reader"));

    const input = screen.getByTestId(
      "play-prompt-input"
    ) as HTMLTextAreaElement;
    expect(input).toHaveValue("play @board-reader mid");
    expect(input.selectionStart).toBe("play @board-reader".length);
  });

  it("chooses the highlighted skill on Enter instead of submitting", () => {
    const props = renderPromptBox();

    const input = typePrompt("@");
    fireEvent.keyDown(input, { key: "Enter" });

    expect(props.onAttachSkill).toHaveBeenCalledWith("marvel-champions-play");
    expect(props.onSubmit).not.toHaveBeenCalled();
  });

  it("moves the highlight with the arrow keys", () => {
    const props = renderPromptBox();

    const input = typePrompt("@");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(props.onAttachSkill).toHaveBeenCalledWith("board-reader");
  });

  it("closes the picker on Escape and leaves the prompt untouched", () => {
    const props = renderPromptBox();

    const input = typePrompt("@");
    fireEvent.keyDown(input, { key: "Escape" });

    expect(
      screen.queryByTestId("skill-mention-picker")
    ).not.toBeInTheDocument();
    expect(props.onAttachSkill).not.toHaveBeenCalled();
    expect(props.onPromptChange).toHaveBeenCalledTimes(1);
    expect(props.onPromptChange).toHaveBeenCalledWith("@");
  });

  it("still submits on Enter when the picker is closed", () => {
    const props = renderPromptBox({ prompt: "hello" });

    fireEvent.keyDown(screen.getByTestId("play-prompt-input"), {
      key: "Enter",
    });

    expect(props.onSubmit).toHaveBeenCalledOnce();
  });

  it("still offers a skill already attached to the session", () => {
    // A mention loads the skill into *this* message, which is worth repeating on
    // a later turn even though the session attachment is already in place.
    renderPromptBox({ attachedSkills: ["board-reader"] });

    typePrompt("@");

    expect(
      screen.getByTestId("skill-mention-option-board-reader")
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("skill-mention-option-marvel-champions-play")
    ).toBeInTheDocument();
  });

  it("renders no chip row when no skill is attached", () => {
    renderPromptBox();

    expect(
      screen.queryByTestId("composer-skill-chips")
    ).not.toBeInTheDocument();
  });

  it("renders a chip per attached skill and detaches from it", () => {
    const props = renderPromptBox({
      attachedSkills: ["board-reader", "marvel-champions-play"],
    });

    expect(screen.getByTestId("composer-skill-chips")).toBeInTheDocument();
    expect(screen.getByText("board-reader")).toBeInTheDocument();
    expect(screen.getByText("marvel-champions-play")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Detach skill board-reader" })
    );
    expect(props.onDetachSkill).toHaveBeenCalledWith("board-reader");
  });

  it("cannot open the picker without an active session", () => {
    renderPromptBox({ prompt: "@", selectedSession: null });

    // The textarea is disabled, so no mention can be typed and no picker opens.
    expect(screen.getByTestId("play-prompt-input")).toBeDisabled();
    expect(
      screen.queryByTestId("skill-mention-picker")
    ).not.toBeInTheDocument();
  });

  it("disables the detach control without an active session", () => {
    renderPromptBox({
      selectedSession: null,
      attachedSkills: ["board-reader"],
    });

    expect(
      screen.getByRole("button", { name: "Detach skill board-reader" })
    ).toBeDisabled();
  });
});
