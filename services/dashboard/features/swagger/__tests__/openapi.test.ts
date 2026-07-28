import { beforeEach, describe, expect, it, vi } from "vitest";

import { buildMergedOpenApi } from "@/features/swagger/lib/openapi";

// Pinned so the fake fetch below can tell the two upstreams apart regardless of
// what a developer has these variables set to in their shell.
const ORCHESTRATOR_URL = "http://orchestrator.test:4002";
const GAME_SERVICE_URL = "http://game.test:4001";

describe("buildMergedOpenApi", () => {
  beforeEach(() => {
    process.env.AGENT_ORCHESTRATOR_URL = ORCHESTRATOR_URL;
    process.env.GAME_SERVICE_URL = GAME_SERVICE_URL;
  });

  it("prefixes paths, component refs, tags, and operation ids per service", async () => {
    const fetchImpl = vi.fn(async (input: string | URL) => {
      const url = String(input);
      if (url.startsWith(ORCHESTRATOR_URL)) {
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
      const url = String(input);
      if (url.startsWith(ORCHESTRATOR_URL)) {
        return new Response(
          JSON.stringify({ openapi: "3.1.0", paths: {}, components: {} })
        );
      }

      return new Response("boom", { status: 502 });
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
