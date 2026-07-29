## 1. Establish which direction is actually buffered

- [x] 1.1 Read the proxy route and confirm the request side calls
      `await request.arrayBuffer()` while the response side already returns
      `new Response(upstreamResponse.body, …)` — so requests were buffered and
      responses were not.
- [x] 1.2 Confirm empirically, against a production build driven over sockets,
      that a slowly produced upstream response reaches the client in separate
      chunks with the first arriving early (10 chunks; first at 65 ms of a 604 ms
      response), rather than in one piece at the end.
- [x] 1.3 Confirm that `duplex: "half"` is genuinely required by this repository's
      runtime rather than assumed: a `ReadableStream` body without it throws
      `RequestInit: duplex option is required when sending a body` on Node 24.8,
      and note that the requirement dates to Node 18, so no supported version
      omits it.
- [x] 1.4 Confirm Node's `fetch` honours an explicit `content-length` alongside a
      stream body (sends it, does not chunk), which is what lets the upstreams'
      declared-size fast rejection survive streaming.

## 2. Stream the request body

- [x] 2.1 Add `buildProxyRequestInit` to `features/proxy/lib/proxy.ts`, returning
      `request.body` with `duplex: "half"` and never reading the body.
- [x] 2.2 Export a `ProxyRequestInit` intersection carrying `duplex`, since the
      DOM `RequestInit` the dashboard compiles against has no such member — one
      declaration instead of a cast at the call site.
- [x] 2.3 Keep `GET` and `HEAD`, and any bodyless request, sending no body, which
      is what the route did before.
- [x] 2.4 Re-attach a well-formed declared `Content-Length` to the outbound
      request so the upstreams can still refuse an oversized upload before reading
      it; forward nothing when the incoming value is absent or non-numeric.
- [x] 2.5 Call it from the route in place of the `arrayBuffer` read, and document
      at the response line that reading `upstreamResponse.body` is the one edit
      that would silently reintroduce full buffering.
- [x] 2.6 Pin the route `dynamic = "force-dynamic"`: caching a proxied response
      would require buffering it to store it, and nothing here is cacheable.

## 3. Leave the per-service caps as the only ceilings

- [x] 3.1 Add no cap to the proxy, and record in `buildProxyRequestInit`'s
      documentation why: a shared route would have to pick one number for four
      services and flatten the deliberate gap between the orchestrator's 8 MiB and
      history's 64 MiB.
- [x] 3.2 Verify both upstream caps survive a body with no declared length by
      reading their enforcement: the orchestrator's `MaxBodySizeMiddleware`
      rejects once its running total crosses `max_bytes`, and history's
      `BundleReader` checks its running total per chunk. Neither depends on
      `Content-Length`.
- [x] 3.3 Confirm `game-service` and `eval-service` declare no request body cap,
      so streaming removes nothing from them either.

## 4. Fix the two defects the streaming work exposed

- [x] 4.1 Add the missing hop-by-hop headers to `STRIPPED_REQUEST_HEADERS` —
      `transfer-encoding`, `keep-alive`, `proxy-authenticate`,
      `proxy-authorization`, `proxy-connection`, `te`, `trailer`, `upgrade`, and
      `expect` — completing the RFC 9110 set alongside the existing `connection`,
      `content-length`, and `host`.
- [x] 4.2 Record in the comment that forwarding `transfer-encoding` made Node's
      `fetch` refuse the outbound call outright, so every chunked upload failed
      before and after this change, and that two hops disagreeing about where a
      body ends is what request smuggling relies on.
- [x] 4.3 Tighten `assertSafeSegment` to refuse a segment whose percent-decoded
      form contains `/` or `\`, closing `..%2fadmin` and `%2e%2e%2f%2e%2e` — which
      the exact `.`/`..` match let through — while still accepting an ordinary
      dotted segment such as `openapi.json`.

## 5. Cover it with tests that would catch the regression

- [x] 5.1 Add `features/proxy/__tests__/proxy-route.test.ts`, exercising the route
      handler against a real loopback HTTP server on an ephemeral port, because
      whether a body streams is a wire property a stubbed `fetch` cannot observe —
      and an ephemeral port keeps the suite off the developer stack's fixed ports.
- [x] 5.2 Test that a 6 MiB body reaches the upstream while the sender is still
      producing it, and arrives in many chunks; verify this test fails against the
      old `arrayBuffer` implementation.
- [x] 5.3 Test that a request arriving with `Transfer-Encoding: chunked` is
      forwarded successfully; verify this test fails when `transfer-encoding` is
      not stripped.
- [x] 5.4 Test the outbound init directly: a stream body with `duplex: "half"`, no
      body or duplex for `GET`/`HEAD`/bodyless `DELETE`, a forwarded numeric
      `Content-Length`, and a dropped non-numeric one.
- [x] 5.5 Test the response direction: the route returns before the upstream body
      finishes, a multi-megabyte response arrives in many chunks, and the response
      header filter still keeps `content-disposition` while dropping the framing
      headers.
- [x] 5.6 Test that cross-site rejection, foreign-`Origin` rejection, unknown
      service, and every traversal spelling answer without the loopback upstream
      receiving a single request.
- [x] 5.7 Test that a streamed request reaches the upstream without `cookie`,
      `authorization`, or `x-forwarded-*`, with `content-type` intact and `host`
      rewritten.
- [x] 5.8 Extend `features/proxy/__tests__/proxy.test.ts` with the full hop-by-hop
      strip, the decoded-separator rejections, and an ordinary dotted segment that
      must still be accepted.

## 6. Verify against the running application

- [x] 6.1 Build the dashboard for production and drive the proxy over real
      sockets: a 5 MiB chunked upload (upstream saw its first byte at sender chunk
      2 of 40 and received 161 chunks) and a 3 MiB upload with a declared length
      (forwarded as `content-length: 3145728`, no `transfer-encoding`).
- [x] 6.2 Verify the response direction end to end on the same build: a slow
      10-line export arrives as 10 chunks, first at 65 ms of a 604 ms response.
- [x] 6.3 Verify header filtering end to end: nothing from `cookie`,
      `authorization`, or `x-forwarded-*` reaches the upstream; `content-type`
      does; `host` is the upstream's.
- [x] 6.4 Verify cross-site rejection end to end: a `Sec-Fetch-Site: cross-site`
      POST and a foreign-`Origin` GET both answer `403` with the upstream never
      contacted.
- [x] 6.5 Verify traversal rejection over **raw sockets**, so that no client-side
      URL normalisation stands in for the route's own check. Record the finding
      that Next.js normalises `..`, `.`, and their `%2e` spellings before routing —
      `/api/proxy/history/games/../admin` reaches the handler as `["admin"]` and
      stays within the configured base URL — and that the encoded-separator cases
      are the ones the route itself must refuse, which it now does with `400`.

## 7. Keep the surrounding files current

- [x] 7.1 Add a proxy section to `services/dashboard/AGENTS.md` recording the
      pass-through invariant and the header allowlist, since "read the body here"
      is the natural-looking edit that would undo this fix.
- [x] 7.2 Confirm nothing else goes stale: no configuration key is added or
      changed, so `docker-compose.yaml`, `.env.example` files, the service READMEs,
      the root `README.md`, `scripts/`, and the `Makefile` need no edit; the
      history-service README's import section describes its own cap, which is
      unchanged.

## 8. Checks

- [x] 8.1 `./scripts/lint.sh --fix` clean.
- [x] 8.2 `./scripts/test.sh unit` — report counts before and after.
- [x] 8.3 `pnpm typecheck` in `services/dashboard` clean, and `pnpm build`
      succeeds with the proxy route still listed as dynamic.
- [x] 8.4 `openspec validate --all` (the pre-existing `spec/typed-game-actions`
      failure is untouched).
