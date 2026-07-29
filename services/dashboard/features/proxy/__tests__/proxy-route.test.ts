// @vitest-environment node
//
// The proxy route is exercised against a real loopback HTTP server rather than a
// stubbed `fetch`, because the property under test is a wire property: whether a
// body crosses the proxy as it arrives or only after the whole thing is resident
// in the dashboard process. A stub can confirm the shape of the `fetch` init but
// cannot tell those two apart.
import http from "node:http";
import type { AddressInfo } from "node:net";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { DELETE, GET, POST } from "@/app/api/proxy/[service]/[...path]/route";
import { buildProxyRequestInit } from "@/features/proxy/lib/proxy";

type UpstreamCall = {
  method: string;
  url: string;
  headers: http.IncomingHttpHeaders;
  /** Bytes received, counted as they arrive. */
  bytes: number;
  /** Chunk sizes in arrival order, so overlap with the sender is observable. */
  chunks: number[];
};

type Upstream = {
  origin: string;
  calls: UpstreamCall[];
  close: () => Promise<void>;
};

/**
 * A loopback upstream on an ephemeral port. Port 0 keeps the suite clear of the
 * developer stack's fixed ports (3000, 4000-4005, 5440-5443, 6380-6381).
 */
async function startUpstream(
  handle: (
    call: UpstreamCall,
    res: http.ServerResponse
  ) => void | Promise<void> = (_call, res) => {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ ok: true }));
  }
): Promise<Upstream> {
  const calls: UpstreamCall[] = [];
  const server = http.createServer((req, res) => {
    const call: UpstreamCall = {
      method: req.method ?? "",
      url: req.url ?? "",
      headers: req.headers,
      bytes: 0,
      chunks: [],
    };
    calls.push(call);

    req.on("data", (chunk: Buffer) => {
      call.bytes += chunk.length;
      call.chunks.push(chunk.length);
    });
    req.on("end", () => {
      void handle(call, res);
    });
  });

  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;

  return {
    origin: `http://127.0.0.1:${port}`,
    calls,
    close: () =>
      new Promise<void>((resolve, reject) =>
        server.close((error) => (error ? reject(error) : resolve()))
      ),
  };
}

/** A route context whose `params` promise mirrors what Next.js passes in. */
function routeContext(service: string, path: string[]) {
  return { params: Promise.resolve({ service, path }) };
}

const openUpstreams: Upstream[] = [];

/**
 * Start a loopback upstream and point the proxy's history service at it. The
 * proxy resolves upstream base URLs from configuration on every request, so this
 * is all the wiring a route test needs.
 */
async function upstream(
  handle?: Parameters<typeof startUpstream>[0]
): Promise<Upstream> {
  const started = await startUpstream(handle);
  openUpstreams.push(started);
  process.env.HISTORY_SERVICE_URL = started.origin;
  return started;
}

beforeEach(() => {
  // A closed port, so a test that expects the proxy never to reach upstream
  // fails loudly if it does.
  process.env.HISTORY_SERVICE_URL = "http://127.0.0.1:1";
});

afterEach(async () => {
  await Promise.all(openUpstreams.splice(0).map((server) => server.close()));
});

describe("proxy route request streaming", () => {
  it("forwards the incoming body as a stream, never as a buffer", () => {
    const init = buildProxyRequestInit(
      new Request("http://dashboard.local/api/proxy/history/import", {
        method: "POST",
        headers: { "content-type": "application/x-ndjson" },
        body: "line\n",
        duplex: "half",
      } as RequestInit)
    );

    expect(init.body).toBeInstanceOf(ReadableStream);
    // Required by Node's fetch for any stream body; without it the outbound call
    // throws before a byte is sent.
    expect(init.duplex).toBe("half");
  });

  it("sends no body and no duplex for GET and HEAD", () => {
    for (const method of ["GET", "HEAD"]) {
      const init = buildProxyRequestInit(
        new Request("http://dashboard.local/api/proxy/history/games", {
          method,
        })
      );
      expect(init.body).toBeUndefined();
      expect(init.duplex).toBeUndefined();
    }
  });

  it("sends no body and no duplex for a bodyless DELETE", () => {
    const init = buildProxyRequestInit(
      new Request("http://dashboard.local/api/proxy/history/games/g1", {
        method: "DELETE",
      })
    );
    expect(init.body).toBeUndefined();
    expect(init.duplex).toBeUndefined();
  });

  it("re-declares a well-formed Content-Length so upstream size caps can reject early", () => {
    const init = buildProxyRequestInit(
      new Request("http://dashboard.local/api/proxy/history/import", {
        method: "POST",
        headers: { "content-length": "12345" },
        body: "hello",
        duplex: "half",
      } as RequestInit)
    );

    expect(new Headers(init.headers).get("content-length")).toBe("12345");
  });

  it("does not forward a non-numeric Content-Length", () => {
    const init = buildProxyRequestInit(
      new Request("http://dashboard.local/api/proxy/history/import", {
        method: "POST",
        headers: { "content-length": "not-a-number" },
        body: "hello",
        duplex: "half",
      } as RequestInit)
    );

    expect(new Headers(init.headers).has("content-length")).toBe(false);
  });

  it("delivers a large body upstream while the sender is still producing it", async () => {
    const server = await upstream();

    const CHUNK_SIZE = 64 * 1024;
    const CHUNK_COUNT = 96; // 6 MiB, past any plausible single-buffer boundary.
    let produced = 0;
    let producedWhenUpstreamSawFirstByte: number | null = null;

    const body = new ReadableStream<Uint8Array>({
      async pull(controller) {
        if (produced >= CHUNK_COUNT) {
          controller.close();
          return;
        }
        produced += 1;
        if (
          producedWhenUpstreamSawFirstByte === null &&
          (server.calls[0]?.bytes ?? 0) > 0
        ) {
          producedWhenUpstreamSawFirstByte = produced;
        }
        controller.enqueue(new Uint8Array(CHUNK_SIZE).fill(65));
        // Yield to the event loop so the upstream's reads can interleave with
        // production; a buffering proxy would show no interleaving at all.
        await new Promise((resolve) => setTimeout(resolve, 0));
      },
    });

    const response = await POST(
      new Request("http://dashboard.local/api/proxy/history/import", {
        method: "POST",
        headers: { "content-type": "application/x-ndjson" },
        body,
        duplex: "half",
      } as RequestInit),
      routeContext("history", ["import"])
    );

    expect(response.status).toBe(200);
    expect(server.calls).toHaveLength(1);
    expect(server.calls[0].bytes).toBe(CHUNK_SIZE * CHUNK_COUNT);
    // The upstream received bytes before the sender had produced them all: the
    // body was in flight, not resident. Buffering would make this null.
    expect(producedWhenUpstreamSawFirstByte).not.toBeNull();
    expect(producedWhenUpstreamSawFirstByte!).toBeLessThan(CHUNK_COUNT);
    // Arriving in many chunks rather than one is the same fact seen from the
    // receiving end.
    expect(server.calls[0].chunks.length).toBeGreaterThan(1);
  });

  it("forwards a chunked upload whose incoming Transfer-Encoding header is present", async () => {
    // A browser streaming-upload (`fetch` with a ReadableStream body) arrives
    // chunked with no Content-Length. Passing that header through makes Node's
    // fetch reject the outbound call before it opens a socket, so the upload
    // never reaches upstream at all.
    const server = await upstream();

    const response = await POST(
      new Request("http://dashboard.local/api/proxy/history/import", {
        method: "POST",
        headers: {
          "content-type": "application/x-ndjson",
          "transfer-encoding": "chunked",
        },
        body: "line one\nline two\n",
        duplex: "half",
      } as RequestInit),
      routeContext("history", ["import"])
    );

    expect(response.status).toBe(200);
    expect(server.calls[0].bytes).toBe("line one\nline two\n".length);
    expect(server.calls[0].headers["transfer-encoding"]).toBe("chunked");
  });

  it("carries an upstream's declared-size rejection back to the caller", async () => {
    // Stands in for history-service's `HISTORY_IMPORT_MAX_BYTES` fast path and
    // the agent-orchestrator's `MaxBodySizeMiddleware`: both answer 413 off the
    // declared Content-Length, before reading the body. Streaming must not
    // retire that, which is why the proxy re-declares the incoming length — a
    // chunked send would carry no length for the upstream to judge.
    const CAP = 1024;
    const oversized = "x".repeat(CAP * 8);

    const server = await upstream((call, res) => {
      const declared = Number(call.headers["content-length"] ?? "0");
      if (declared > CAP) {
        res.writeHead(413, { "content-type": "application/json" });
        res.end(JSON.stringify({ detail: "Request body too large" }));
        return;
      }
      res.writeHead(200, { "content-type": "application/json" });
      res.end("{}");
    });

    const response = await POST(
      new Request("http://dashboard.local/api/proxy/history/import", {
        method: "POST",
        headers: {
          "content-type": "application/x-ndjson",
          "content-length": String(oversized.length),
        },
        body: oversized,
        duplex: "half",
      } as RequestInit),
      routeContext("history", ["import"])
    );

    expect(response.status).toBe(413);
    await expect(response.json()).resolves.toEqual({
      detail: "Request body too large",
    });
    expect(server.calls[0].headers["content-length"]).toBe(
      String(oversized.length)
    );
  });
});

describe("proxy route response streaming", () => {
  it("returns the upstream response before its body has finished arriving", async () => {
    let releaseTail: () => void = () => {};
    const tail = new Promise<void>((resolve) => {
      releaseTail = resolve;
    });

    const server = await upstream(async (_call, res) => {
      res.writeHead(200, { "content-type": "application/x-ndjson" });
      res.write("head\n");
      await tail;
      res.end("tail\n");
    });

    const response = await GET(
      new Request(`http://dashboard.local/api/proxy/history/games/g1/export`),
      routeContext("history", ["games", "g1", "export"])
    );

    // The route handed back a response while the upstream was still writing —
    // proof the body is a live stream and not a buffered payload.
    expect(response.status).toBe(200);
    expect(response.body).not.toBeNull();

    const reader = response.body!.getReader();
    const first = await reader.read();
    expect(new TextDecoder().decode(first.value)).toBe("head\n");

    releaseTail();

    let rest = "";
    for (;;) {
      const next = await reader.read();
      if (next.done) break;
      rest += new TextDecoder().decode(next.value);
    }
    expect(rest).toBe("tail\n");
    expect(server.calls[0].method).toBe("GET");
  });

  it("streams a multi-megabyte response through in many chunks", async () => {
    const CHUNK = "n".repeat(64 * 1024);
    const COUNT = 64; // 4 MiB.

    await upstream((_call, res) => {
      res.writeHead(200, { "content-type": "application/x-ndjson" });
      let written = 0;
      const pump = () => {
        while (written < COUNT) {
          written += 1;
          if (!res.write(CHUNK)) {
            res.once("drain", pump);
            return;
          }
        }
        res.end();
      };
      pump();
    });

    const response = await GET(
      new Request("http://dashboard.local/api/proxy/history/games/g1/export"),
      routeContext("history", ["games", "g1", "export"])
    );

    const reader = response.body!.getReader();
    let received = 0;
    let chunkCount = 0;
    for (;;) {
      const next = await reader.read();
      if (next.done) break;
      received += next.value.byteLength;
      chunkCount += 1;
    }

    expect(received).toBe(CHUNK.length * COUNT);
    expect(chunkCount).toBeGreaterThan(1);
  });

  it("applies response header filtering to a streamed response", async () => {
    await upstream((_call, res) => {
      res.writeHead(200, {
        "content-type": "application/x-ndjson",
        "content-disposition": 'attachment; filename="game.ndjson"',
        "x-history-format": "dragncards-ai.game-history",
      });
      res.end("{}\n");
    });

    const response = await GET(
      new Request("http://dashboard.local/api/proxy/history/games/g1/export"),
      routeContext("history", ["games", "g1", "export"])
    );

    // Kept: the download filename and any upstream metadata.
    expect(response.headers.get("content-disposition")).toBe(
      'attachment; filename="game.ndjson"'
    );
    expect(response.headers.get("x-history-format")).toBe(
      "dragncards-ai.game-history"
    );
    // Dropped: framing headers that describe the upstream hop, not this one.
    expect(response.headers.has("transfer-encoding")).toBe(false);
    expect(response.headers.has("content-encoding")).toBe(false);
    expect(response.headers.has("content-length")).toBe(false);
    await response.body?.cancel();
  });
});

describe("proxy route security is unchanged by streaming", () => {
  it("rejects a cross-site request without contacting upstream", async () => {
    const server = await upstream();

    const response = await POST(
      new Request("http://dashboard.local/api/proxy/history/import", {
        method: "POST",
        headers: {
          "sec-fetch-site": "cross-site",
          "content-type": "application/x-ndjson",
        },
        body: "line\n",
        duplex: "half",
      } as RequestInit),
      routeContext("history", ["import"])
    );

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual({
      detail: "Cross-site proxy requests are not allowed",
    });
    expect(server.calls).toHaveLength(0);
  });

  it("rejects a same-site request from another origin without contacting upstream", async () => {
    const server = await upstream();

    const response = await GET(
      new Request("http://dashboard.local/api/proxy/history/games", {
        headers: { origin: "http://evil.example.com" },
      }),
      routeContext("history", ["games"])
    );

    expect(response.status).toBe(403);
    expect(server.calls).toHaveLength(0);
  });

  it("rejects traversal path segments, literal and percent-encoded, without contacting upstream", async () => {
    const server = await upstream();

    for (const segments of [
      ["games", "..", "admin"],
      ["games", "."],
      ["games", "%2e%2e", "admin"],
    ]) {
      const response = await GET(
        new Request("http://dashboard.local/api/proxy/history/games"),
        routeContext("history", segments)
      );
      expect(response.status).toBe(400);
      const payload = (await response.json()) as { detail: string };
      expect(payload.detail).toMatch(/invalid proxy path segment/i);
    }

    expect(server.calls).toHaveLength(0);
  });

  it("rejects an unknown service without contacting upstream", async () => {
    const server = await upstream();

    const response = await GET(
      new Request("http://dashboard.local/api/proxy/nope/games"),
      routeContext("nope", ["games"])
    );

    expect(response.status).toBe(404);
    expect(server.calls).toHaveLength(0);
  });

  it("strips credentials and forwarding metadata from a streamed request", async () => {
    const server = await upstream();

    await POST(
      new Request("http://dashboard.local/api/proxy/history/import", {
        method: "POST",
        headers: {
          "content-type": "application/x-ndjson",
          cookie: "session=secret",
          authorization: "Bearer token",
          "x-forwarded-for": "1.2.3.4",
          "x-forwarded-host": "evil.example.com",
        },
        body: "line\n",
        duplex: "half",
      } as RequestInit),
      routeContext("history", ["import"])
    );

    const [call] = server.calls;
    expect(call.headers["content-type"]).toBe("application/x-ndjson");
    expect(call.headers.cookie).toBeUndefined();
    expect(call.headers.authorization).toBeUndefined();
    expect(call.headers["x-forwarded-for"]).toBeUndefined();
    expect(call.headers["x-forwarded-host"]).toBeUndefined();
    // Host is rewritten for the upstream hop rather than forwarded.
    expect(call.headers.host).not.toBe("dashboard.local");
  });

  it("forwards the query string and method for a bodyless DELETE", async () => {
    const server = await upstream();

    const response = await DELETE(
      new Request("http://dashboard.local/api/proxy/history/games/g1?force=1", {
        method: "DELETE",
      }),
      routeContext("history", ["games", "g1"])
    );

    expect(response.status).toBe(200);
    expect(server.calls[0].method).toBe("DELETE");
    expect(server.calls[0].url).toBe("/games/g1?force=1");
    expect(server.calls[0].bytes).toBe(0);
  });
});

beforeEach(() => {
  process.env.HISTORY_SERVICE_URL = "http://127.0.0.1:1";
});
