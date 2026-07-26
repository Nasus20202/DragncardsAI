import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import { ConversationTranscript } from "@/features/history/components/conversation-transcript";
import { JsonValue } from "@/features/shared/lib/types";

const context: JsonValue = [
  { role: "system", content: "You are a Marvel Champions bot." },
  { role: "user", content: "It is your turn." },
  {
    role: "assistant",
    content: "I'll play Spider-Man.",
    tool_calls: [
      {
        id: "call_1",
        function: { name: "play_card", arguments: '{"card":"spider-man"}' },
      },
    ],
  },
  { role: "tool", tool_call_id: "call_1", content: '{"status":"ok"}' },
];

describe("ConversationTranscript", () => {
  it("renders an empty hint when there is no conversation", () => {
    render(<ConversationTranscript context={null} />);
    expect(screen.getByTestId("transcript-empty")).toBeInTheDocument();
  });

  it("renders message bubbles, tool call, and tool result as a transcript", () => {
    render(<ConversationTranscript context={context} />);

    expect(screen.getByTestId("conversation-transcript")).toBeInTheDocument();
    expect(screen.getByTestId("transcript-user")).toHaveTextContent(
      "It is your turn."
    );
    expect(screen.getByTestId("transcript-assistant")).toHaveTextContent(
      "I'll play Spider-Man."
    );

    // Tool call card present and labelled with the tool name.
    const call = screen.getByTestId("transcript-tool-call");
    expect(call).toHaveTextContent("Tool call: play_card");

    // Tool result card resolves the tool name from the call.
    const result = screen.getByTestId("transcript-tool-result");
    expect(result).toHaveTextContent("Tool result: play_card");

    // System prompt is rendered as a collapsible card (collapsed by default,
    // so its body is hidden until expanded).
    const systemCard = screen.getByTestId("transcript-system");
    expect(systemCard).toHaveTextContent("System prompt");
    expect(
      screen.queryByText("You are a Marvel Champions bot.")
    ).not.toBeInTheDocument();

    // Expanding the tool-call card reveals its arguments.
    fireEvent.click(screen.getByRole("button", { name: /Expand Tool call/i }));
    expect(call).toHaveTextContent('"card": "spider-man"');
  });
});
