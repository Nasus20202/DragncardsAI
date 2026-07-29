import { beforeEach, describe, expect, it, vi } from "vitest";

import { SERVICE_KEYS, ServiceKey } from "@/features/proxy/lib/proxy";
import { buildMergedOpenApi } from "@/features/swagger/lib/openapi";

// Pinned so the fake fetch below can tell the upstreams apart regardless of what
// a developer has these variables set to in their shell.
const ORCHESTRATOR_URL = "http://orchestrator.test:4002";
const GAME_SERVICE_URL = "http://game.test:4001";
const HISTORY_SERVICE_URL = "http://history.test:4004";
const EVAL_SERVICE_URL = "http://eval.test:4005";

const SERVICE_BASE_URLS: Record<ServiceKey, string> = {
  orchestrator: ORCHESTRATOR_URL,
  game: GAME_SERVICE_URL,
  history: HISTORY_SERVICE_URL,
  eval: EVAL_SERVICE_URL,
};

function serviceForUrl(input: string | URL): ServiceKey {
  const url = String(input);
  const match = SERVICE_KEYS.find((service) =>
    url.startsWith(SERVICE_BASE_URLS[service])
  );
  if (!match) {
    throw new Error(`Unexpected OpenAPI fetch to ${url}`);
  }

  return match;
}

describe("buildMergedOpenApi", () => {
  beforeEach(() => {
    process.env.AGENT_ORCHESTRATOR_URL = ORCHESTRATOR_URL;
    process.env.GAME_SERVICE_URL = GAME_SERVICE_URL;
    process.env.HISTORY_SERVICE_URL = HISTORY_SERVICE_URL;
    process.env.EVAL_SERVICE_URL = EVAL_SERVICE_URL;
  });

  // The regression guard for DRA-20: the index used to walk a hardcoded
  // ["orchestrator", "game"] list, so history-service and eval-service were
  // reachable through the proxy yet absent from Swagger. Driving the assertion
  // from SERVICE_KEYS means dropping any service from the merge — or resolving
  // it against another service's base url — fails here.
  it("includes every service the proxy fronts, each from its own base url", async () => {
    const fetchImpl = vi.fn(async (input: string | URL) => {
      const service = serviceForUrl(input);
      return new Response(
        JSON.stringify({
          openapi: "3.1.0",
          paths: { [`/probe-${service}`]: { get: { operationId: "probe" } } },
        })
      );
    });

    const result = await buildMergedOpenApi(fetchImpl as typeof fetch);

    expect(result.errors).toEqual([]);
    for (const service of SERVICE_KEYS) {
      expect(result.document.paths).toHaveProperty(
        `/${service}/probe-${service}`
      );
    }

    expect(fetchImpl.mock.calls.map(([input]) => String(input)).sort()).toEqual(
      SERVICE_KEYS.map(
        (service) => `${SERVICE_BASE_URLS[service]}/openapi.json`
      ).sort()
    );
  });

  it("honours a per-service OpenAPI path override", async () => {
    process.env.HISTORY_SERVICE_OPENAPI_PATH = "/api/history-openapi.json";
    const fetchImpl = vi.fn(async (input: string | URL) => {
      serviceForUrl(input);
      return new Response(JSON.stringify({ openapi: "3.1.0", paths: {} }));
    });

    try {
      await buildMergedOpenApi(fetchImpl as typeof fetch);
    } finally {
      delete process.env.HISTORY_SERVICE_OPENAPI_PATH;
    }

    expect(fetchImpl.mock.calls.map(([input]) => String(input))).toContain(
      `${HISTORY_SERVICE_URL}/api/history-openapi.json`
    );
  });

  it("prefixes paths, component refs, tags, and operation ids per service", async () => {
    const fetchImpl = vi.fn(async (input: string | URL) => {
      const service = serviceForUrl(input);
      if (service === "orchestrator") {
        return new Response(
          JSON.stringify({
            openapi: "3.1.0",
            paths: {
              "/sessions": {
                get: {
                  operationId: "list_sessions",
                  tags: ["sessions"],
                  responses: {
                    "200": {
                      content: {
                        "application/json": {
                          schema: {
                            $ref: "#/components/schemas/SessionListResponse",
                          },
                        },
                      },
                    },
                  },
                },
              },
            },
            tags: [{ name: "sessions" }],
            components: {
              schemas: {
                SessionListResponse: {
                  type: "object",
                },
              },
            },
          })
        );
      }

      if (service === "game") {
        return new Response(
          JSON.stringify({
            openapi: "3.1.0",
            paths: {
              "/games": {
                get: {
                  operationId: "list_games",
                  tags: ["game-lifecycle"],
                },
              },
            },
            tags: [{ name: "game-lifecycle" }],
            components: {
              schemas: {
                SessionListResponse: {
                  type: "object",
                },
              },
            },
          })
        );
      }

      return new Response(JSON.stringify({ openapi: "3.1.0", paths: {} }));
    });

    const result = await buildMergedOpenApi(fetchImpl as typeof fetch);
    const document = result.document;

    expect(document.paths).toMatchObject({
      "/orchestrator/sessions": {
        get: {
          operationId: "orchestrator_list_sessions",
          tags: ["orchestrator:sessions"],
        },
      },
      "/game/games": {
        get: {
          operationId: "game_list_games",
          tags: ["game:game-lifecycle"],
        },
      },
    });

    const components = document.components as Record<
      string,
      Record<string, unknown>
    >;
    expect(components.schemas).toHaveProperty(
      "orchestrator_SessionListResponse"
    );
    expect(components.schemas).toHaveProperty("game_SessionListResponse");

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const paths = document.paths as Record<string, any>;
    const orchestratorSchema =
      paths["/orchestrator/sessions"]?.get?.responses?.["200"]?.content?.[
        "application/json"
      ]?.schema;
    expect(orchestratorSchema).toEqual({
      $ref: "#/components/schemas/orchestrator_SessionListResponse",
    });
  });

  it("collects errors and keeps available specs", async () => {
    const fetchImpl = vi.fn(async (input: string | URL) => {
      if (serviceForUrl(input) === "game") {
        return new Response("boom", { status: 502 });
      }

      return new Response(
        JSON.stringify({ openapi: "3.1.0", paths: {}, components: {} })
      );
    });

    const result = await buildMergedOpenApi(fetchImpl as typeof fetch);
    expect(result.errors).toEqual([
      {
        service: "game",
        message: "game OpenAPI request failed with status 502",
      },
    ]);
    expect(result.document["x-dashboard-errors"]).toEqual(result.errors);
  });
});
