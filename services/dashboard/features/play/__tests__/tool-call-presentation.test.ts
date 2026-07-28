import { describe, expect, it } from "vitest";

import { JobEventResponse, JsonValue } from "@/features/shared/lib/types";
import {
  BODY_VALUE_CHARS,
  REDACTED,
  SUMMARY_CHARS,
  argumentText,
  boundedArgumentText,
  boundedResultText,
  boundedValueText,
  buildToolExchangeView,
  isSecretArgumentName,
  presentationForTool,
  redactSecrets,
  shortId,
  stringifyBounded,
  subagentReference,
  toolResultText,
  toolValueText,
} from "@/features/play/lib/tool-call-presentation";

function callEvent(
  payload: Record<string, JsonValue>,
  id = "call-event"
): JobEventResponse {
  return {
    id,
    event_type: "tool_call",
    payload,
    created_at: "2026-07-28T00:00:00Z",
  };
}

function resultEvent(
  payload: Record<string, JsonValue>,
  id = "result-event"
): JobEventResponse {
  return {
    id,
    event_type: "tool_result",
    payload,
    created_at: "2026-07-28T00:00:01Z",
  };
}

function textResult(text: string, isError = false): Record<string, JsonValue> {
  return {
    tool_call_id: "call-1",
    exposed_tool_name: "tool",
    is_error: isError,
    result: { is_error: isError, content: [{ type: "text", text }] },
  };
}

describe("redactSecrets", () => {
  it("redacts credentials in every shape a tool result carries them", () => {
    expect(redactSecrets("Authorization: Bearer abc123def456")).toBe(
      `Authorization: ${REDACTED}`
    );
    expect(redactSecrets('{"api_key": "super-secret-value"}')).toContain(
      REDACTED
    );
    expect(redactSecrets('{"api_key": "super-secret-value"}')).not.toContain(
      "super-secret-value"
    );
    expect(redactSecrets("X-BF-API-Key=abcdefgh")).toBe(
      `X-BF-API-Key=${REDACTED}`
    );
    expect(redactSecrets("tried bearer sk-live-9999")).toBe(
      `tried Bearer ${REDACTED}`
    );
    expect(redactSecrets("provider rejected sk-ant-abcdefghijklmnopqrst")).toBe(
      `provider rejected ${REDACTED}`
    );
    expect(redactSecrets("key AIzaSyABCDEFGHIJKL used")).toBe(
      `key ${REDACTED} used`
    );
  });

  it("leaves prose that merely mentions a secret alone", () => {
    expect(redactSecrets("the secret is wrong")).toBe("the secret is wrong");
    expect(redactSecrets("")).toBe("");
  });
});

describe("stringifyBounded", () => {
  it("stops reading once the budget is spent", () => {
    const huge: JsonValue = Array.from({ length: 50_000 }, (_, i) => ({
      card_id: `card-${i}`,
      name: "A very long card name that makes each entry expensive to print",
    }));

    const bounded = stringifyBounded(huge, 500);

    expect(bounded.truncated).toBe(true);
    expect(bounded.text.length).toBeLessThanOrEqual(500);
    // Only the first entries were ever visited.
    expect(bounded.text).toContain("card-0");
    expect(bounded.text).not.toContain("card-40000");
  });

  it("prints small values in full, like JSON.stringify would", () => {
    const value: JsonValue = { a: 1, b: [true, null], c: "x" };
    expect(stringifyBounded(value, 10_000)).toEqual({
      text: JSON.stringify(value, null, 2),
      truncated: false,
    });
    expect(stringifyBounded([], 100).text).toBe("[]");
    expect(stringifyBounded({}, 100).text).toBe("{}");
  });
});

describe("boundedValueText", () => {
  it("shows strings raw and other values pretty-printed", () => {
    expect(boundedValueText("plain prompt text", 100).text).toBe(
      "plain prompt text"
    );
    expect(boundedValueText({ a: 1 }, 100).text).toBe('{\n  "a": 1\n}');
  });

  it("caps the text and reports that it did", () => {
    const long = "x".repeat(5_000);
    const bounded = boundedValueText(long, 100);
    expect(bounded.truncated).toBe(true);
    expect(bounded.text.length).toBeLessThanOrEqual(100);
  });

  it("redacts a credential sitting past the displayed window", () => {
    // The credential is beyond the cap but inside the redaction slack, so it
    // must be replaced rather than merely cut in half.
    const text = `${"padding ".repeat(10)}api_key=super-secret-token-value`;
    const bounded = boundedValueText(text, 40);
    expect(bounded.text).not.toContain("super-secret-token-value");
  });

  it("drops the token the cut landed inside", () => {
    const text = `${"a ".repeat(30)}trailingtoken`;
    const bounded = boundedValueText(text, 62);
    expect(bounded.text.endsWith("trailing")).toBe(false);
  });
});

describe("named arguments whose name says they hold a credential", () => {
  it("redacts the value whether previewed or shown in full", () => {
    // `redactSecrets` matches a credential by the field name in front of it, and
    // an argument row renders the name and the value as two separate pieces of
    // text — so the name has to be matched on its own.
    for (const name of [
      "api_key",
      "API-KEY",
      "authorization",
      "access_token",
      "client_secret",
      "password",
      "token",
      "credentials",
    ]) {
      expect(isSecretArgumentName(name)).toBe(true);
      expect(boundedArgumentText(name, "hunter2hunter2", 100).text).toBe(
        REDACTED
      );
      expect(argumentText(name, "hunter2hunter2")).toBe(REDACTED);
    }
  });

  it("leaves ordinary argument names alone", () => {
    expect(isSecretArgumentName("card_id")).toBe(false);
    expect(isSecretArgumentName("prompt")).toBe(false);
    expect(boundedArgumentText("card_id", "01001a", 100).text).toBe("01001a");
    expect(argumentText("card_id", "01001a")).toBe("01001a");
  });

  it("keeps such an argument out of the collapsed summary too", () => {
    const view = buildToolExchangeView(
      callEvent({
        exposed_tool_name: "call_vendor",
        arguments: { api_key: "hunter2hunter2", endpoint: "/cards" },
      }),
      null
    );
    expect(view.summary).not.toContain("hunter2");
    expect(view.summary).toContain(REDACTED);
    expect(view.summary).toContain("endpoint: /cards");
  });
});

describe("toolValueText", () => {
  it("returns the whole value, redacted", () => {
    expect(toolValueText("api_key=leaked-value-here")).toBe(
      `api_key=${REDACTED}`
    );
    expect(toolValueText({ a: [1, 2] })).toBe(
      JSON.stringify({ a: [1, 2] }, null, 2)
    );
  });
});

describe("buildToolExchangeView", () => {
  it("names the tool, lists its arguments, and summarises them in one line", () => {
    const view = buildToolExchangeView(
      callEvent({
        tool_call_id: "call-1",
        exposed_tool_name: "move_card",
        tool_name: "mcp_move_card",
        assignment: "game-service",
        server_url: "http://game-service:8000/mcp",
        arguments: { card_id: "01001a", dest_group_id: "player1Play" },
      }),
      resultEvent(textResult("moved"))
    );

    expect(view.toolName).toBe("move_card");
    expect(view.server).toBe("game-service");
    expect(view.toolCallId).toBe("call-1");
    expect(view.args.map((arg) => arg.name)).toEqual([
      "card_id",
      "dest_group_id",
    ]);
    expect(view.summary).toBe("card_id: 01001a  ·  dest_group_id: player1Play");
    expect(view.status).toBe("ok");
    expect(view.resultChars).toBe("moved".length);
    expect(view.errorPreview).toBeNull();
  });

  it("reports a call with no result yet as pending", () => {
    const view = buildToolExchangeView(
      callEvent({ exposed_tool_name: "get_game_state", arguments: {} }),
      null
    );
    expect(view.status).toBe("pending");
    expect(view.args).toEqual([]);
    expect(view.summary).toBe("");
  });

  it("reports an error result and previews it without expanding", () => {
    const view = buildToolExchangeView(
      callEvent({ exposed_tool_name: "draw_card", arguments: { count: 1 } }),
      resultEvent(textResult("upstream refused: api_key=leaked-key", true))
    );
    expect(view.status).toBe("error");
    expect(view.errorPreview).toContain("upstream refused");
    expect(view.errorPreview).not.toContain("leaked-key");
  });

  it("summarises nested arguments by shape, never by serialising them", () => {
    const view = buildToolExchangeView(
      callEvent({
        exposed_tool_name: "load_cards",
        arguments: {
          cards: Array.from({ length: 40_000 }, (_, i) => `card-${i}`),
          options: { shuffle: true },
        },
      }),
      null
    );
    expect(view.summary).toBe("cards: [40000 items]  ·  options: {…}");
    expect(view.summary.length).toBeLessThanOrEqual(SUMMARY_CHARS);
  });

  it("keeps the summary bounded when a scalar argument is enormous", () => {
    const view = buildToolExchangeView(
      callEvent({
        exposed_tool_name: "spawn_subagent",
        arguments: { prompt: "y".repeat(400_000) },
      }),
      null
    );
    expect(view.summary.length).toBeLessThanOrEqual(SUMMARY_CHARS);
    expect(view.summary.startsWith("prompt: yyy")).toBe(true);
  });

  it("falls back to the payload text when a call carries no arguments object", () => {
    const view = buildToolExchangeView(
      callEvent({ exposed_tool_name: "legacy", text: "raw body" }),
      null
    );
    expect(view.args).toEqual([]);
    expect(view.callFallback).toBe("raw body");
    expect(view.summary).toBe("raw body");
  });

  it("redacts a token carried in the MCP server URL it reports", () => {
    const view = buildToolExchangeView(
      callEvent({
        exposed_tool_name: "vendor_tool",
        assignment: null,
        server_url:
          "https://mcp.vendor.example/mcp?api_key=sk-live-abcdefghijkl",
        arguments: {},
      }),
      null
    );
    expect(view.server).toContain(REDACTED);
    expect(view.server).not.toContain("sk-live-abcdefghijkl");
  });

  it("renders a result that arrived without its call", () => {
    const view = buildToolExchangeView(null, resultEvent(textResult("orphan")));
    expect(view.toolName).toBe("tool");
    expect(view.status).toBe("ok");
  });
});

describe("boundedResultText and toolResultText", () => {
  it("reads the orchestrator's content-part shape", () => {
    const result = resultEvent(textResult("first"));
    expect(boundedResultText(result, 100).text).toBe("first");
    expect(toolResultText(result)).toBe("first");
  });

  it("bounds a huge result and redacts what it shows", () => {
    const result = resultEvent(
      textResult(`api_key=leaked-token ${"z".repeat(500_000)}`)
    );
    const bounded = boundedResultText(result, 200);
    expect(bounded.truncated).toBe(true);
    expect(bounded.text.length).toBeLessThanOrEqual(200);
    expect(bounded.text).not.toContain("leaked-token");
  });

  it("falls back to the raw payload when there is no content part", () => {
    const result = resultEvent({ tool_call_id: "c", unexpected: true });
    expect(toolResultText(result)).toContain("unexpected");
    expect(boundedResultText(result, BODY_VALUE_CHARS).text).toContain(
      "unexpected"
    );
  });
});

describe("subagentReference", () => {
  it("reads the child a launch started out of its result", () => {
    const reference = subagentReference(
      callEvent({
        exposed_tool_name: "spawn_subagent",
        arguments: { prompt: "look up the villain deck" },
      }),
      resultEvent(
        textResult(
          JSON.stringify({ child_job_id: "child-123", name: "look up the" })
        )
      )
    );
    expect(reference).toEqual({
      childJobId: "child-123",
      name: "look up the",
      playerId: null,
    });
  });

  it("reads the child a wait is blocked on out of its arguments", () => {
    const reference = subagentReference(
      callEvent({
        exposed_tool_name: "wait_for_subagent",
        arguments: { child_job_id: "child-456" },
      }),
      null
    );
    expect(reference?.childJobId).toBe("child-456");
  });

  it("keeps the seat a player prompt was sent to", () => {
    const reference = subagentReference(
      callEvent({
        exposed_tool_name: "prompt_player_agent",
        arguments: { player_id: "player2", prompt: "take your turn" },
      }),
      resultEvent(
        textResult(
          JSON.stringify({
            child_job_id: "child-789",
            name: "Spider-Man",
            player_id: "player2",
          })
        )
      )
    );
    expect(reference).toEqual({
      childJobId: "child-789",
      name: "Spider-Man",
      playerId: "player2",
    });
  });

  it("rejects a child id that is not shaped like a job id", () => {
    // The id reaches a request path in the subagent view, and a
    // `wait_for_subagent` argument is written by the model.
    for (const forged of [
      "x/../../../eval/targets?foo=1#",
      "child 123",
      "child.123",
      "a".repeat(65),
      "",
    ]) {
      expect(
        subagentReference(
          callEvent({
            exposed_tool_name: "wait_for_subagent",
            arguments: { child_job_id: forged },
          }),
          null
        )
      ).toBeNull();
    }
  });

  it("returns nothing when no child can be identified", () => {
    expect(
      subagentReference(
        callEvent({ exposed_tool_name: "spawn_subagent", arguments: {} }),
        resultEvent(textResult("prompt is required.", true))
      )
    ).toBeNull();
  });
});

describe("presentationForTool", () => {
  it("maps the system tools to their bespoke presentations", () => {
    expect(presentationForTool("spawn_subagent")).toBe("subagent_launch");
    expect(presentationForTool("prompt_player_agent")).toBe("subagent_launch");
    expect(presentationForTool("wait_for_subagent")).toBe("subagent_wait");
    expect(presentationForTool("load_skill")).toBe("skill_load");
    expect(presentationForTool("load_skill_reference")).toBe("skill_load");
  });

  it("falls back to the generic presentation for everything else", () => {
    expect(presentationForTool("list_player_agents")).toBe("generic");
    expect(presentationForTool("search_cards_marvel_champions")).toBe(
      "generic"
    );
    expect(presentationForTool("")).toBe("generic");
  });
});

describe("shortId", () => {
  it("shortens long ids and leaves short ones alone", () => {
    expect(shortId("0123456789abcdef")).toBe("01234567…");
    expect(shortId("abc")).toBe("abc");
  });
});
