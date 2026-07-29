# Stream request and response bodies through the shared dashboard proxy

## Why

DRA-27 reports, verbatim:

> The shared dashboard proxy route
> `services/dashboard/app/api/proxy/[service]/[...path]/route.ts` does
> `await request.arrayBuffer()`, which buffers the entire request body in the
> Next.js process before forwarding it.

Every browser call the dashboard makes to a first-party service goes through that
one route: agent-orchestrator, game-service, history-service, and eval-service.
It read each request body into an `ArrayBuffer` before opening the outbound
`fetch`, so the whole upload became resident in the dashboard process — however
carefully the upstream was written to stream.

The measured cost is not hypothetical. A lossless history export of a real
124-event game is **31 MB** of NDJSON, because every `game-service` event embeds a
complete DragnCards board state. history-service's `POST /import` was built for
exactly that: it validates and writes the bundle line by line and enforces
`HISTORY_IMPORT_MAX_BYTES` (64 MiB) against a running byte total inside its
reader, never holding the file. A direct `POST` to `:4004/import` streams from end
to end. The same bundle imported *through the dashboard UI* — the path a user
actually takes — was buffered whole by the proxy first, so the streaming was
defeated on precisely the journey it was designed for.

Two things had to be established rather than assumed, and both were, against a
production build of the dashboard driven over real sockets:

- **Requests were buffered; responses were not.** The route already returned
  `new Response(upstreamResponse.body, …)`, handing the upstream stream on unread.
  A 10-line export dribbled at 60 ms intervals reached the client in 10 separate
  chunks with the first arriving after 65 ms of a 604 ms response. The export
  direction was sound; only the import direction was broken.
- **Next.js does not buffer the body before the handler runs.** With the fix, a
  5 MiB upload sent in 40 chunks reached the upstream in 161 chunks, the first
  arriving while the sender was still on chunk 2. `request.body` in a Next.js 16
  route handler is a live stream, so streaming it onward is all that was needed.

## What Changes

### The request body is forwarded as a stream

A new `buildProxyRequestInit` in `features/proxy/lib/proxy.ts` builds the outbound
`fetch` init and passes `request.body` straight through, with `duplex: "half"`.

`duplex: "half"` is not optional and not cosmetic: Node's `fetch` (undici) throws
`RequestInit: duplex option is required when sending a body` for **any**
`ReadableStream` body, before opening a socket. Confirmed on this repository's
Node 24.8 and Next.js 16.2.12; it has been required since streaming request
bodies landed in undici (Node 18), so no version in use here can omit it. The DOM
`RequestInit` that the dashboard's `lib: ["dom"]` provides has no `duplex` member,
so an exported `ProxyRequestInit` intersection declares it once rather than
casting at the call site.

`GET` and `HEAD`, and any request that arrives with no body, keep sending no body
at all — the behaviour the route already had.

### Per-service size caps stay separate, and stay enforceable

The proxy takes **no size ceiling of its own**. Each upstream keeps the only cap
that governs it, and they differ deliberately: the agent-orchestrator's
`MAX_REQUEST_BODY_BYTES` (8 MiB) and history-service's `HISTORY_IMPORT_MAX_BYTES`
(64 MiB). Streaming leaves both fully enforced, because neither depends on
`Content-Length` to enforce them: the orchestrator's ASGI `MaxBodySizeMiddleware`
rejects as soon as its running total crosses the limit, and history's
`BundleReader` does the same per chunk. A ceiling in the shared proxy would have
to pick one number for four services and would flatten exactly the distinction
the issue asks to preserve.

Both upstreams *additionally* reject an oversized upload on its declared
`Content-Length` before reading a byte, and that fast rejection needed protecting.
`filterProxyRequestHeaders` strips `content-length` as hop-by-hop, and a streamed
body makes Node's `fetch` fall back to `Transfer-Encoding: chunked` — which
carries no length for an upstream to judge, silently retiring the fast path. So a
well-formed declared length is re-attached to the outbound request. This is safe
rather than a smuggling vector: HTTP/1.1 framing means the incoming stream yields
exactly the declared number of bytes, and Node's `fetch` honours an explicit
`content-length` alongside a stream body instead of chunking (verified: a 3 MiB
upload arrives with `content-length: 3145728` and no `transfer-encoding`). A
missing or non-numeric value is simply not forwarded, and the upstreams' byte
counting covers that case as it always has.

### Two defects the streaming work exposed

Neither was in the issue; both were found by driving a production build over real
sockets, and both are fixed here because a streaming proxy is where they bite.

**`transfer-encoding` was never stripped.** It is absent from
`STRIPPED_REQUEST_HEADERS`, so a request that arrived chunked had that header
forwarded — and Node's `fetch` refuses such a request outright with
`InvalidArgumentError: invalid transfer-encoding header`. Every chunked upload
through the proxy therefore failed, before and after this change. It went
unnoticed because `fetch(…, { body: file })` sets `Content-Length`, so the
existing UI never sent chunked; a browser streaming-upload does. The fix completes
the header set to the whole RFC 9110 hop-by-hop list — `connection`, `keep-alive`,
`proxy-authenticate`, `proxy-authorization`, `te`, `trailer`,
`transfer-encoding`, `upgrade` — plus `content-length`, the non-standard
`proxy-connection`, and `expect`. These describe the browser-to-dashboard hop and
say nothing about the dashboard-to-upstream one, whose framing Node's `fetch`
decides for itself. Forwarding `transfer-encoding` is also the shape a request
smuggling attempt needs: two hops disagreeing about where a body ends.

**A path segment could decode to a path.** `assertSafeSegment` rejected a segment
that is or decodes to exactly `.` or `..`. A segment like `..%2fadmin` is neither,
yet decodes to `../admin`; likewise `%2e%2e%2f%2e%2e` decodes to `../..`. Those
could not actually traverse — `encodeURIComponent` re-encodes the slash, so the
wire carried one opaque segment and the upstream saw `/games/..%2Fadmin` rather
than `/admin` — but the guarantee rested on the encoder rather than on the guard,
and the guard's own comment claimed more than it checked. A segment whose decoded
form contains `/` or `\` is now refused with `400`, which is not a restriction any
real proxy path meets: no dashboard caller needs a separator inside one segment.

### What the verification established about the surrounding behaviour

Driven against a production build over raw sockets, so that no client-side URL
normalisation could stand in for the route's own checks:

- Next.js normalises `..`, `.`, and their `%2e` spellings in the request path
  *before* routing, so `/api/proxy/history/games/../admin` reaches the handler as
  the segment list `["admin"]` and is proxied to `/admin` — within the configured
  history-service base URL, never above it. The route's guard covers what
  normalisation leaves behind, which is where the encoded-separator cases lived.
- Cross-site rejection still fires before any upstream contact: a
  `Sec-Fetch-Site: cross-site` POST and a foreign-`Origin` GET both answer `403`
  with the upstream never receiving a connection.
- Header filtering still applies to a streamed request: `cookie`,
  `authorization`, and `x-forwarded-*` do not reach the upstream, `content-type`
  does, and `host` is rewritten for the outbound hop.
- The response filter still applies to a streamed response: `content-disposition`
  (the export filename) and upstream metadata survive, while
  `content-encoding`, `content-length`, and `transfer-encoding` are dropped.

The route is also pinned `dynamic = "force-dynamic"`. Caching a proxied response
would require Next.js to buffer it in order to store it, and nothing here is
cacheable — every response belongs to one caller's request. Pinning it states that
outright instead of leaving it to depend on which dynamic APIs the handler happens
to touch.

## Non-goals

- Adding a size ceiling, quota, or rate limit to the proxy. The per-service caps
  are the only ones, and keeping it that way is the point.
- Changing `MAX_REQUEST_BODY_BYTES`, `HISTORY_IMPORT_MAX_BYTES`, or either
  upstream's enforcement of them.
- Replacing the orchestrator's `MaxBodySizeMiddleware`. It buffers in order to
  replay, which is the same defect in another place, but it is that service's
  concern and its cap is enforced against a running total either way.
- Adding authentication, per-service authorization, or an upstream path allowlist
  to the proxy. The cross-site check and the segment guard are unchanged in
  purpose.
- Buffering, transforming, decompressing, or inspecting any proxied payload. The
  proxy stays a pass-through.
- Touching the history export/import UI, the Swagger playground, or the SSE job
  feed. All three benefit from the fix without changing.

## Impact

- Affected specs: `dashboard` (a streaming proxy that buffers neither direction,
  keeps per-service caps as the only ceilings, and preserves its cross-site,
  path-segment, and header-filtering behaviour under streaming).
- Affected code:
  - `services/dashboard/features/proxy/lib/proxy.ts` — new
    `buildProxyRequestInit` and `ProxyRequestInit`, the completed hop-by-hop
    header set, and the tightened `assertSafeSegment`.
  - `services/dashboard/app/api/proxy/[service]/[...path]/route.ts` — forwards
    the streamed init, pins the route dynamic, and documents that reading
    `upstreamResponse.body` is the one edit that would silently reintroduce
    buffering.
  - `services/dashboard/features/proxy/__tests__/proxy.test.ts` and
    `features/proxy/__tests__/proxy-route.test.ts` (new) — the route handler is
    now covered against a real loopback upstream, because whether a body streams
    is a wire property a stubbed `fetch` cannot observe.
  - `services/dashboard/AGENTS.md` — records the pass-through invariant, since
    "read the body here" is the natural-looking edit that would undo this.
- No new configuration. No dependency, migration, Dockerfile, or compose change:
  the fix is a different `fetch` init on an existing route. `docker-compose.yaml`
  already passes each service its own cap, and those values are unchanged.
- The proxy now depends on `duplex: "half"` being supported by the runtime's
  `fetch`. That is satisfied by Node 18 and above; the dashboard image and this
  repository both run Node 24, and `package.json` pins Next.js 16.2.12, so no
  supported configuration lacks it.
- Behaviour change a caller could notice: a request whose path segment decodes to
  something containing `/` or `\` now answers `400` instead of being forwarded as
  an opaque encoded segment for the upstream to reject. No dashboard feature
  constructs such a path.
