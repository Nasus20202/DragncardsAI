import { describe, expect, it } from "vitest";

import {
  filterProxyRequestHeaders,
  filterProxyResponseHeaders,
  resolveProxyUrl,
} from "@/features/proxy/lib/proxy";

describe("resolveProxyUrl", () => {
  it("maps orchestrator paths under the configured base url", () => {
    const url = resolveProxyUrl("orchestrator", ["sessions", "abc"], "?limit=10");
    expect(String(url)).toBe("http://localhost:8010/sessions/abc?limit=10");
  });

  it("maps game service paths under the configured base url", () => {
    const url = resolveProxyUrl("game", ["games", "state"], "");
    expect(String(url)).toBe("http://localhost:8000/games/state");
  });
});

describe("proxy header filtering", () => {
  it("removes hop-by-hop request headers", () => {
    const headers = new Headers({
      accept: "application/json",
      host: "example.com",
      connection: "keep-alive",
      "content-length": "100",
    });

    const filtered = filterProxyRequestHeaders(headers);
    expect(filtered.get("accept")).toBe("application/json");
    expect(filtered.has("host")).toBe(false);
    expect(filtered.has("connection")).toBe(false);
    expect(filtered.has("content-length")).toBe(false);
  });

  it("removes streaming and encoded response headers that should be recomputed", () => {
    const headers = new Headers({
      "content-type": "text/event-stream",
      "content-encoding": "gzip",
      "transfer-encoding": "chunked",
      "content-length": "42",
    });

    const filtered = filterProxyResponseHeaders(headers);
    expect(filtered.get("content-type")).toBe("text/event-stream");
    expect(filtered.has("content-encoding")).toBe(false);
    expect(filtered.has("transfer-encoding")).toBe(false);
    expect(filtered.has("content-length")).toBe(false);
  });
});
