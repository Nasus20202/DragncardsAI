import { logs } from "@opentelemetry/api-logs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  createServerLogger,
  createLogRecordProcessors,
} from "../lib/server-logging";
import { withServerSpan } from "../lib/server-tracing";

describe("server logging", () => {
  beforeEach(() => {
    process.env.NEXT_RUNTIME = "nodejs";
  });

  afterEach(() => {
    delete process.env.NEXT_RUNTIME;
    vi.restoreAllMocks();
  });

  it("creates OTLP log processors for the node runtime", () => {
    expect(createLogRecordProcessors()).toHaveLength(1);
  });

  it("emits logger output through the app logger", () => {
    const emit = vi.fn();
    vi.spyOn(logs, "getLogger").mockReturnValue({ emit } as never);
    const logger = createServerLogger("dashboard.test");

    logger.error("request failed", {
      route: "/api/test",
      "error.message": "boom",
    });

    expect(emit).toHaveBeenCalledTimes(1);
    expect(emit).toHaveBeenCalledWith(
      expect.objectContaining({
        severityText: "ERROR",
        body: "request failed",
        attributes: expect.objectContaining({
          "log.type": "app",
          route: "/api/test",
          "error.message": "boom",
        }),
      })
    );
  });

  it("does not emit logs just because a span exists", async () => {
    const emit = vi.fn();
    vi.spyOn(logs, "getLogger").mockReturnValue({ emit } as never);

    const result = await withServerSpan(
      "dashboard.test",
      { route: "/api/test" },
      async () => "ok"
    );

    expect(result).toBe("ok");
    expect(emit).not.toHaveBeenCalled();
  });

  it("still records span failures without forcing log output", async () => {
    await expect(
      withServerSpan("dashboard.test", { route: "/api/test" }, async () => {
        throw new Error("boom");
      })
    ).rejects.toThrow("boom");
  });

  it("does not create processors outside the node runtime", () => {
    process.env.NEXT_RUNTIME = "edge";

    expect(createLogRecordProcessors()).toHaveLength(0);
  });
});
