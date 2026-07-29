import { beforeEach, describe, expect, it } from "vitest";

import {
  SERVICE_KEYS,
  filterProxyRequestHeaders,
  filterProxyResponseHeaders,
  getServiceBaseUrl,
  isCrossSiteRequest,
  isServiceKey,
  resolveProxyUrl,
} from "@/features/proxy/lib/proxy";
import { withServerSpan } from "@/features/observability/lib/server-tracing";

// Deliberately not the localhost defaults: pinning distinctive base urls proves
// the proxy resolves them from configuration, and keeps the expectations correct
// for a developer who has the stack's service urls exported in their shell.
const ORCHESTRATOR_URL = "http://orchestrator.test:4002";
const GAME_SERVICE_URL = "http://game.test:4001";
const HISTORY_SERVICE_URL = "http://history.test:4004";
const EVAL_SERVICE_URL = "http://eval.test:4005";

// The test setup clears these before every test, so every suite that resolves an
// upstream url sets them back.
beforeEach(() => {
  process.env.AGENT_ORCHESTRATOR_URL = ORCHESTRATOR_URL;
  process.env.GAME_SERVICE_URL = GAME_SERVICE_URL;
  process.env.HISTORY_SERVICE_URL = HISTORY_SERVICE_URL;
  process.env.EVAL_SERVICE_URL = EVAL_SERVICE_URL;
});

describe("resolveProxyUrl", () => {
  it("maps orchestrator paths under the configured base url", () => {
    const url = resolveProxyUrl(
      "orchestrator",
      ["sessions", "abc"],
      "?limit=10"
    );
    expect(String(url)).toBe(`${ORCHESTRATOR_URL}/sessions/abc?limit=10`);
  });

  it("maps game service paths under the configured base url", () => {
    const url = resolveProxyUrl("game", ["games", "state"], "");
    expect(String(url)).toBe(`${GAME_SERVICE_URL}/games/state`);
  });

  it("maps history service paths under the configured base url", () => {
    const url = resolveProxyUrl(
      "history",
      ["games", "game-1", "events"],
      "?after_seq=3"
    );
    expect(String(url)).toBe(
      `${HISTORY_SERVICE_URL}/games/game-1/events?after_seq=3`
    );
  });

  it("maps eval service paths under the configured base url", () => {
    const url = resolveProxyUrl("eval", ["games", "game-1", "evaluations"], "");
    expect(String(url)).toBe(`${EVAL_SERVICE_URL}/games/game-1/evaluations`);
  });

  it("rejects a literal '..' path segment", () => {
    expect(() =>
      resolveProxyUrl("history", ["games", "..", "admin"], "")
    ).toThrow(/invalid proxy path segment/i);
  });

  it("rejects a literal '.' path segment", () => {
    expect(() => resolveProxyUrl("history", ["games", "."], "")).toThrow(
      /invalid proxy path segment/i
    );
  });

  it("rejects percent-encoded '..' (%2e%2e) path segments", () => {
    expect(() =>
      resolveProxyUrl("history", ["games", "%2e%2e", "admin"], "")
    ).toThrow(/invalid proxy path segment/i);
  });

  it("rejects a segment that percent-decodes to a path containing a separator", () => {
    // Neither "." nor "..", so the exact-match check alone passes it, yet it
    // decodes to "../admin". Refusing it here means the traversal guarantee does
    // not depend on `encodeURIComponent` re-encoding the slash downstream.
    expect(() =>
      resolveProxyUrl("history", ["games", "..%2fadmin"], "")
    ).toThrow(/invalid proxy path segment/i);
    expect(() =>
      resolveProxyUrl("history", ["%2e%2e%2f%2e%2e", "etc", "passwd"], "")
    ).toThrow(/invalid proxy path segment/i);
    expect(() => resolveProxyUrl("history", ["games", "a%5Cb"], "")).toThrow(
      /invalid proxy path segment/i
    );
  });

  it("keeps accepting ordinary segments that merely contain a dot", () => {
    const url = resolveProxyUrl("history", ["games", "g1", "openapi.json"], "");
    expect(String(url)).toBe(`${HISTORY_SERVICE_URL}/games/g1/openapi.json`);
  });

  it("rejects a path segment that fails to percent-decode", () => {
    expect(() => resolveProxyUrl("history", ["games", "%E0%A4%A"], "")).toThrow(
      /invalid proxy path segment/i
    );
  });
});

describe("isServiceKey", () => {
  it("accepts the history service key", () => {
    expect(isServiceKey("history")).toBe(true);
    expect(isServiceKey("nope")).toBe(false);
  });

  it("accepts the eval service key", () => {
    expect(isServiceKey("eval")).toBe(true);
  });

  it("accepts exactly the declared service keys", () => {
    expect([...SERVICE_KEYS]).toEqual([
      "orchestrator",
      "game",
      "history",
      "eval",
    ]);
    for (const service of SERVICE_KEYS) {
      expect(isServiceKey(service)).toBe(true);
    }
  });
});

describe("getServiceBaseUrl", () => {
  // A branch chain that falls through would give two service keys the same
  // upstream, which is how history and eval could have been merged from the
  // game-service document without anything failing.
  it("gives every declared service key its own configured base url", () => {
    expect(SERVICE_KEYS.map((service) => getServiceBaseUrl(service))).toEqual([
      ORCHESTRATOR_URL,
      GAME_SERVICE_URL,
      HISTORY_SERVICE_URL,
      EVAL_SERVICE_URL,
    ]);
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

  it("removes the whole hop-by-hop set, so the outbound hop frames its own body", () => {
    // `transfer-encoding` is the load-bearing one: Node's fetch refuses a request
    // that carries it ("invalid transfer-encoding header"), so forwarding it
    // failed every chunked upload — and a proxy that lets two hops disagree about
    // where a body ends is the shape a request-smuggling attempt needs.
    const headers = new Headers({
      "content-type": "application/x-ndjson",
      "transfer-encoding": "chunked",
      "keep-alive": "timeout=5",
      "proxy-connection": "keep-alive",
      "proxy-authorization": "Basic Zm9v",
      "proxy-authenticate": "Basic",
      te: "trailers",
      trailer: "x-checksum",
      upgrade: "websocket",
      expect: "100-continue",
    });

    const filtered = filterProxyRequestHeaders(headers);
    expect(filtered.get("content-type")).toBe("application/x-ndjson");
    for (const name of [
      "transfer-encoding",
      "keep-alive",
      "proxy-connection",
      "proxy-authorization",
      "proxy-authenticate",
      "te",
      "trailer",
      "upgrade",
      "expect",
    ]) {
      expect(filtered.has(name), `${name} should be stripped`).toBe(false);
    }
  });

  it("strips browser credentials and forwarding metadata, keeping content-type", () => {
    const headers = new Headers({
      "content-type": "application/json",
      cookie: "session=secret",
      authorization: "Bearer token",
      "x-forwarded-for": "1.2.3.4",
      "x-forwarded-host": "evil.example.com",
      "x-forwarded-proto": "https",
    });

    const filtered = filterProxyRequestHeaders(headers);
    expect(filtered.get("content-type")).toBe("application/json");
    expect(filtered.has("cookie")).toBe(false);
    expect(filtered.has("authorization")).toBe(false);
    expect(filtered.has("x-forwarded-for")).toBe(false);
    expect(filtered.has("x-forwarded-host")).toBe(false);
    expect(filtered.has("x-forwarded-proto")).toBe(false);
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

describe("isCrossSiteRequest", () => {
  function request(headers: Record<string, string>): Request {
    return new Request("http://dashboard.local/api/proxy/eval/games", {
      headers,
    });
  }

  it("allows requests with no Origin / Sec-Fetch headers (server-to-server)", () => {
    expect(isCrossSiteRequest(request({}))).toBe(false);
  });

  it("allows Sec-Fetch-Site: same-origin and none", () => {
    expect(
      isCrossSiteRequest(request({ "sec-fetch-site": "same-origin" }))
    ).toBe(false);
    expect(isCrossSiteRequest(request({ "sec-fetch-site": "none" }))).toBe(
      false
    );
  });

  it("rejects Sec-Fetch-Site: cross-site and same-site", () => {
    expect(
      isCrossSiteRequest(request({ "sec-fetch-site": "cross-site" }))
    ).toBe(true);
    expect(isCrossSiteRequest(request({ "sec-fetch-site": "same-site" }))).toBe(
      true
    );
  });

  it("falls back to Origin host comparison when Sec-Fetch-Site is absent", () => {
    expect(
      isCrossSiteRequest(request({ origin: "http://dashboard.local" }))
    ).toBe(false);
    expect(
      isCrossSiteRequest(request({ origin: "http://evil.example.com" }))
    ).toBe(true);
  });

  it("rejects an unparseable Origin", () => {
    expect(isCrossSiteRequest(request({ origin: "not a url" }))).toBe(true);
  });
});

describe("withServerSpan", () => {
  it("returns the wrapped result", async () => {
    const result = await withServerSpan(
      "dashboard.test",
      { "test.enabled": true },
      async () => "ok"
    );

    expect(result).toBe("ok");
  });
});
