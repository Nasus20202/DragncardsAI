import { describe, expect, it } from "vitest";

import { readJson } from "@/features/history/lib/http";

function errorResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/**
 * The realistic reference-selection failure: the eval-service refuses an
 * over-budget selection with a 400 whose `detail` is one long string naming the
 * measured total, the budget, every reserve term, and the settings that would
 * raise it. All of it has to survive the trip to the user -- a truncated or
 * summarised version would strip exactly the numbers that make it actionable.
 */
const BUDGET_REFUSAL =
  "selected skill references total at least 313317 characters, over the 248549 " +
  "character budget by 64768; references are never truncated. The budget is what " +
  "is left of a 128000-token context window (~512000 chars at ~4 chars/token) " +
  "after reserving 4096 for the completion, 40000 for game state, 120000 for " +
  "round context, 8000 for the prompt frame, 0 for the prompt override, and " +
  "91355 for 5 selected SKILL.md file(s). Deselect references or skills, lower " +
  "EVAL_JUDGE_MOVE_CONTEXT_BEFORE / EVAL_JUDGE_MOVE_CONTEXT_AFTER or " +
  "EVAL_JUDGE_MAX_STATE_CHARS, or set EVAL_JUDGE_CONTEXT_WINDOW_TOKENS to your " +
  "judge model's real context window.";

describe("readJson error details", () => {
  it("passes a plain string detail through", async () => {
    await expect(
      readJson(
        errorResponse(400, { detail: "skill reference cannot be resolved" })
      )
    ).rejects.toThrow("skill reference cannot be resolved");
  });

  it("passes the whole reference-budget refusal through intact", async () => {
    const promise = readJson(errorResponse(400, { detail: BUDGET_REFUSAL }));

    await expect(promise).rejects.toThrow(BUDGET_REFUSAL);
    // The parts that make it actionable, spelled out so a future truncation or
    // summarisation of long details fails here.
    await expect(promise).rejects.toThrow("313317");
    await expect(promise).rejects.toThrow("248549");
    await expect(promise).rejects.toThrow("EVAL_JUDGE_CONTEXT_WINDOW_TOKENS");
  });

  it("renders a FastAPI validation detail array instead of [object Object]", async () => {
    // Schema-level limits still answer with a validation array (the reference
    // count ceiling is now a sanity bound a human cannot reach, but other
    // fields' limits reach this path). Interpolating the array used to surface
    // as "[object Object]", leaving the user with no idea what was wrong.
    const promise = readJson(
      errorResponse(422, {
        detail: [
          {
            type: "too_long",
            loc: ["body", "judge", "skill_references"],
            msg: "List should have at most 1000 items after validation, not 1001",
          },
        ],
      })
    );
    await expect(promise).rejects.toThrow(
      "judge.skill_references: List should have at most 1000 items after validation, not 1001"
    );
    await expect(promise).rejects.not.toThrow("[object Object]");
  });

  it("joins multiple validation entries", async () => {
    await expect(
      readJson(
        errorResponse(422, {
          detail: [
            { loc: ["body", "a"], msg: "first" },
            { loc: ["body", "b"], msg: "second" },
          ],
        })
      )
    ).rejects.toThrow("a: first; b: second");
  });

  it("falls back to the status line when the detail is unusable", async () => {
    await expect(readJson(errorResponse(503, { detail: [] }))).rejects.toThrow(
      "503"
    );
    await expect(
      readJson(new Response("nonsense", { status: 500 }))
    ).rejects.toThrow("500");
  });
});
