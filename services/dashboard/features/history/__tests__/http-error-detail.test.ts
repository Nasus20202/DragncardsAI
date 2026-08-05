import { describe, expect, it } from "vitest";

import { readJson } from "@/features/history/lib/http";

function errorResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("readJson error details", () => {
  it("passes a plain string detail through", async () => {
    await expect(
      readJson(
        errorResponse(400, { detail: "skill reference cannot be resolved" })
      )
    ).rejects.toThrow("skill reference cannot be resolved");
  });

  it("renders a FastAPI validation detail array instead of [object Object]", async () => {
    // What the server actually returns when more than MAX_SKILL_REFERENCES are
    // selected. Interpolating the array used to surface as "[object Object]",
    // leaving the user with no idea what was wrong.
    const promise = readJson(
      errorResponse(422, {
        detail: [
          {
            type: "too_long",
            loc: ["body", "judge", "skill_references"],
            msg: "List should have at most 8 items after validation, not 9",
          },
        ],
      })
    );
    await expect(promise).rejects.toThrow(
      "judge.skill_references: List should have at most 8 items after validation, not 9"
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
