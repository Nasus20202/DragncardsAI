import { afterEach, describe, expect, it, vi } from "vitest";

import {
  cancelEvaluation,
  getEvaluationRequest,
  listEvaluations,
  requestEvaluation,
} from "@/features/history/lib/eval-api";
import { EvaluationRequestBody } from "@/features/shared/lib/types";

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    statusText: ok ? "OK" : "Error",
    json: async () => body,
  } as unknown as Response;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("eval-api client", () => {
  it("posts an evaluation request through the eval proxy", async () => {
    const body: EvaluationRequestBody = {
      scope: "move",
      selection: { seqs: [12] },
      force: false,
    };
    const ack = {
      request_id: "req-1",
      game_id: "game 1",
      scope: "move",
      created_count: 1,
      skipped_count: 0,
      targets: [
        { target_seq: 12, scope: "move", round_span: null, status: "pending" },
      ],
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(ack, true, 201));
    vi.stubGlobal("fetch", fetchMock);

    const result = await requestEvaluation("game 1", body);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/eval/games/game%201/evaluations",
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }
    );
    expect(result).toEqual(ack);
  });

  it("fetches the status of a request through the eval proxy", async () => {
    const status = {
      request_id: "req-1",
      game_id: "game-1",
      status: "completed",
      targets: [
        {
          target_seq: 12,
          scope: "move",
          round_span: null,
          status: "completed",
          verdict: { overall_score: 7 },
          error: null,
        },
      ],
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(status));
    vi.stubGlobal("fetch", fetchMock);

    const result = await getEvaluationRequest("game-1", "req-1");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/eval/games/game-1/evaluations/req-1",
      { cache: "no-store" }
    );
    expect(result).toEqual(status);
  });

  it("posts a judge config with the evaluation request", async () => {
    const body: EvaluationRequestBody = {
      scope: "move",
      selection: { seqs: [1] },
      force: false,
      judge: {
        provider_id: "openrouter",
        model_name: "openrouter/google/gemma:free",
        reasoning: { enabled: true, effort: "high" },
        skills: ["marvel-champions-core-rules"],
      },
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ request_id: "r" }, true, 201));
    vi.stubGlobal("fetch", fetchMock);

    await requestEvaluation("g1", body);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/eval/games/g1/evaluations",
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }
    );
  });

  it("cancels an in-flight evaluation through the eval proxy", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ request_id: "req-1", cancelled: 2 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await cancelEvaluation("game-1", "req-1");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/eval/games/game-1/evaluations/req-1/cancel",
      { method: "POST" }
    );
    expect(result).toEqual({ request_id: "req-1", cancelled: 2 });
  });

  it("lists cross-game evaluations through the eval proxy with query params", async () => {
    const listing = {
      requests: [
        {
          request_id: "req-1",
          game_id: "g1",
          status: "running",
          created_at: "2026-06-28T00:00:00Z",
          targets: [
            {
              target_seq: 12,
              scope: "move",
              round_span: null,
              status: "running",
            },
          ],
        },
      ],
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(listing));
    vi.stubGlobal("fetch", fetchMock);

    const result = await listEvaluations({ active: true, limit: 25 });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/eval/evaluations?active=true&limit=25",
      { cache: "no-store" }
    );
    expect(result).toEqual(listing);
  });

  it("lists evaluations with no query params when no options are given", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ requests: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await listEvaluations();

    expect(fetchMock).toHaveBeenCalledWith("/api/proxy/eval/evaluations", {
      cache: "no-store",
    });
  });

  it("throws with the error detail on a non-ok response", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ detail: "no events" }, false, 404));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      requestEvaluation("game-1", { scope: "move", selection: { seqs: [1] } })
    ).rejects.toThrow("no events");
  });
});
