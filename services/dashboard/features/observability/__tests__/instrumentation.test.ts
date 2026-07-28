import { describe, expect, it } from "vitest";

import { propagateContextUrls } from "../../../instrumentation";

describe("trace-context propagation targets", () => {
  it("covers every first-party backend the dashboard proxies to", () => {
    // A backend missing here gets its own disconnected trace instead of a child
    // span, which is how history-service and eval-service were invisible in
    // dashboard-initiated traces (DRA-23).
    const urls = propagateContextUrls(undefined);

    for (const service of [
      "agent-orchestrator",
      "game-service",
      "history-service",
      "eval-service",
    ]) {
      expect(urls).toContain(service);
    }
  });

  it("covers the host ports a direct local run uses", () => {
    const urls = propagateContextUrls(undefined);

    expect(urls).toContain("localhost:4001");
    expect(urls).toContain("localhost:4002");
    expect(urls).toContain("localhost:4004");
    expect(urls).toContain("localhost:4005");
  });

  it("appends the built-in targets to the configured ones", () => {
    const urls = propagateContextUrls(
      "https://extra.example, , https://two.example"
    );

    expect(urls.slice(0, 2)).toEqual([
      "https://extra.example",
      "https://two.example",
    ]);
    expect(urls).toContain("game-service");
  });

  it("returns only the built-in targets when nothing is configured", () => {
    expect(propagateContextUrls("")).toContain("eval-service");
    expect(propagateContextUrls(undefined)).not.toContain("");
  });
});
