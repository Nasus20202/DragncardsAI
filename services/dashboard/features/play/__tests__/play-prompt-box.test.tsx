import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import { PlayPromptBox } from "@/features/play/components/play-prompt-box";
import { ContextMetadata, SessionDetail } from "@/features/shared/lib/types";

vi.mock("@/features/play/components/context-health-widget", () => ({
  ContextHealthWidget: ({ onCompact }: { onCompact: () => void }) => (
    <button type="button" onClick={onCompact}>
      Compact context
    </button>
  ),
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

const metadata: ContextMetadata = {
  tokens_used: 1,
  context_window_size: 10,
  usage_ratio: 0.1,
  compaction_count: 0,
  last_compacted_at: null,
  multi_turn_memory: true,
  token_breakdown: {
    system_prompt: 1,
    replay: 0,
    tools: 0,
  },
};

describe("PlayPromptBox", () => {
  it("disables input and send button without an active session", () => {
    render(
      <PlayPromptBox
        prompt="hello"
        selectedSession={null}
        activeJobId={null}
        isBusy={false}
        cancelPending={false}
        contextMetadata={null}
        skills={[]}
        attachedSkills={[]}
        onPromptChange={vi.fn()}
        onSubmit={vi.fn()}
        onCancelExecution={vi.fn()}
        onCompact={vi.fn()}
        onAttachSkill={vi.fn()}
        onDetachSkill={vi.fn()}
      />
    );

    expect(screen.getByLabelText("Message")).toBeDisabled();
    expect(screen.getByTestId("play-prompt-input")).toBeDisabled();
    expect(
      screen.getByPlaceholderText("Select an active session to start.")
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /send message/i })
    ).toBeDisabled();
  });

  it("submits on Enter but not Shift+Enter", () => {
    const onSubmit = vi.fn();

    render(
      <PlayPromptBox
        prompt="hello"
        selectedSession={activeSession}
        activeJobId={null}
        isBusy={false}
        cancelPending={false}
        contextMetadata={null}
        skills={[]}
        attachedSkills={[]}
        onPromptChange={vi.fn()}
        onSubmit={onSubmit}
        onCancelExecution={vi.fn()}
        onCompact={vi.fn()}
        onAttachSkill={vi.fn()}
        onDetachSkill={vi.fn()}
      />
    );

    const input = screen.getByLabelText("Message");
    expect(screen.getByTestId("play-prompt-send")).toBeInTheDocument();
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });

    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("shows the compact widget when context metadata is available", () => {
    const onCompact = vi.fn();

    render(
      <PlayPromptBox
        prompt="hello"
        selectedSession={activeSession}
        activeJobId={null}
        isBusy={false}
        cancelPending={false}
        contextMetadata={metadata}
        skills={[]}
        attachedSkills={[]}
        onPromptChange={vi.fn()}
        onSubmit={vi.fn()}
        onCancelExecution={vi.fn()}
        onCompact={onCompact}
        onAttachSkill={vi.fn()}
        onDetachSkill={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /compact context/i }));
    expect(onCompact).toHaveBeenCalledOnce();
  });

  it("disables send while busy", () => {
    render(
      <PlayPromptBox
        prompt="hello"
        selectedSession={activeSession}
        activeJobId={null}
        isBusy={true}
        cancelPending={false}
        contextMetadata={null}
        skills={[]}
        attachedSkills={[]}
        onPromptChange={vi.fn()}
        onSubmit={vi.fn()}
        onCancelExecution={vi.fn()}
        onCompact={vi.fn()}
        onAttachSkill={vi.fn()}
        onDetachSkill={vi.fn()}
      />
    );

    expect(
      screen.getByRole("button", { name: /send message/i })
    ).toBeDisabled();
  });

  it("uses a simple prompt-left context-right layout without a balancing spacer", () => {
    const { container } = render(
      <PlayPromptBox
        prompt="hello"
        selectedSession={activeSession}
        activeJobId={null}
        isBusy={false}
        cancelPending={false}
        contextMetadata={metadata}
        skills={[]}
        attachedSkills={[]}
        onPromptChange={vi.fn()}
        onSubmit={vi.fn()}
        onCancelExecution={vi.fn()}
        onCompact={vi.fn()}
        onAttachSkill={vi.fn()}
        onDetachSkill={vi.fn()}
      />
    );

    const layoutRow = container.querySelector(".lg\\:flex-row");
    const contextColumn = container.querySelector(".lg\\:w-56");
    expect(layoutRow).toBeInTheDocument();
    expect(contextColumn).toBeInTheDocument();
    expect(container.querySelector(".xl\\:w-48")).toBeNull();
  });

  it("shows a cancel button for the active execution", () => {
    const onCancelExecution = vi.fn();

    render(
      <PlayPromptBox
        prompt="hello"
        selectedSession={activeSession}
        activeJobId="job-1"
        isBusy={false}
        cancelPending={false}
        contextMetadata={null}
        skills={[]}
        attachedSkills={[]}
        onPromptChange={vi.fn()}
        onSubmit={vi.fn()}
        onCancelExecution={onCancelExecution}
        onCompact={vi.fn()}
        onAttachSkill={vi.fn()}
        onDetachSkill={vi.fn()}
      />
    );

    fireEvent.click(
      screen.getByRole("button", { name: /cancel active execution/i })
    );
    expect(onCancelExecution).toHaveBeenCalledOnce();
  });

  it("disables cancellation after a cancellation request is pending", () => {
    render(
      <PlayPromptBox
        prompt="hello"
        selectedSession={activeSession}
        activeJobId="job-1"
        isBusy={false}
        cancelPending={true}
        contextMetadata={null}
        skills={[]}
        attachedSkills={[]}
        onPromptChange={vi.fn()}
        onSubmit={vi.fn()}
        onCancelExecution={vi.fn()}
        onCompact={vi.fn()}
        onAttachSkill={vi.fn()}
        onDetachSkill={vi.fn()}
      />
    );

    expect(
      screen.getByRole("button", { name: /cancel active execution/i })
    ).toBeDisabled();
    expect(screen.getByText("Cancelling...")).toBeInTheDocument();
  });
});
