import { describe, expect, it } from "vitest";

import {
  mapConversationToTranscript,
  TranscriptItem,
} from "@/features/history/lib/conversation-transcript";

function kinds(items: TranscriptItem[]): string[] {
  return items.map((item) => item.kind);
}

describe("mapConversationToTranscript", () => {
  it("returns [] for non-array / missing context", () => {
    expect(mapConversationToTranscript(null)).toEqual([]);
    expect(mapConversationToTranscript(undefined)).toEqual([]);
    expect(mapConversationToTranscript("not-an-array")).toEqual([]);
    expect(mapConversationToTranscript({ role: "user" })).toEqual([]);
  });

  it("maps system/user/assistant messages in order", () => {
    const items = mapConversationToTranscript([
      { role: "system", content: "You are a bot." },
      { role: "user", content: "Your turn." },
      { role: "assistant", content: "Playing Spider-Man." },
    ]);

    expect(kinds(items)).toEqual(["system", "user", "assistant"]);
    expect(items[0]).toMatchObject({ kind: "system", text: "You are a bot." });
    expect(items[1]).toMatchObject({ kind: "user", text: "Your turn." });
    expect(items[2]).toMatchObject({
      kind: "assistant",
      text: "Playing Spider-Man.",
    });
  });

  it("flattens array-style content parts into text", () => {
    const items = mapConversationToTranscript([
      {
        role: "user",
        content: [
          { type: "text", text: "line one" },
          { type: "text", text: "line two" },
        ],
      },
    ]);
    expect(items[0]).toMatchObject({
      kind: "user",
      text: "line one\nline two",
    });
  });

  it("emits an assistant tool_call paired with its tool result", () => {
    const items = mapConversationToTranscript([
      { role: "user", content: "Move a card." },
      {
        role: "assistant",
        content: "I'll move it.",
        tool_calls: [
          {
            id: "call_1",
            function: {
              name: "move_card",
              arguments: '{"card":"spider-man","to":"hand"}',
            },
          },
        ],
      },
      {
        role: "tool",
        tool_call_id: "call_1",
        content: '{"ok":true}',
      },
    ]);

    expect(kinds(items)).toEqual([
      "user",
      "assistant",
      "tool_call",
      "tool_result",
    ]);

    const call = items[2];
    expect(call.kind).toBe("tool_call");
    if (call.kind === "tool_call") {
      expect(call.call.id).toBe("call_1");
      expect(call.call.name).toBe("move_card");
      // arguments pretty-printed from the JSON string.
      expect(call.call.arguments).toContain('"card": "spider-man"');
    }

    const result = items[3];
    expect(result.kind).toBe("tool_result");
    if (result.kind === "tool_result") {
      expect(result.toolCallId).toBe("call_1");
      // name resolved from the originating tool_call.
      expect(result.name).toBe("move_card");
      expect(result.text).toBe('{"ok":true}');
    }
  });

  it("handles multiple tool_calls on one assistant message", () => {
    const items = mapConversationToTranscript([
      {
        role: "assistant",
        content: "",
        tool_calls: [
          { id: "a", function: { name: "first", arguments: "{}" } },
          { id: "b", function: { name: "second", arguments: "{}" } },
        ],
      },
      { role: "tool", tool_call_id: "b", content: "second-done" },
    ]);

    expect(kinds(items)).toEqual(["tool_call", "tool_call", "tool_result"]);
    const result = items[2];
    if (result.kind === "tool_result") {
      expect(result.name).toBe("second");
    }
  });

  it("falls back to a raw string for unparseable tool arguments", () => {
    const items = mapConversationToTranscript([
      {
        role: "assistant",
        content: "",
        tool_calls: [
          { id: "x", function: { name: "raw", arguments: "not json" } },
        ],
      },
    ]);
    const call = items[0];
    if (call.kind === "tool_call") {
      expect(call.call.arguments).toBe("not json");
    }
  });

  it("uses the tool message `name` when no matching tool_call id exists", () => {
    const items = mapConversationToTranscript([
      { role: "tool", tool_call_id: "orphan", name: "lookup", content: "x" },
    ]);
    const result = items[0];
    expect(result.kind).toBe("tool_result");
    if (result.kind === "tool_result") {
      expect(result.name).toBe("lookup");
      expect(result.toolCallId).toBe("orphan");
    }
  });
});
