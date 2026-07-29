## ADDED Requirements

### Requirement: The service proxy streams both directions and buffers neither

The dashboard's shared service proxy route SHALL forward a request body as the
stream it received, and SHALL forward an upstream response body as the stream the
upstream produced. It SHALL NOT read either body into a buffer, a string, or any
in-memory structure before forwarding it.

Because Node's `fetch` rejects any `ReadableStream` body sent without it, the
outbound request SHALL declare `duplex: "half"`.

A request whose method admits no body (`GET`, `HEAD`), and a request that arrives
carrying no body, SHALL be forwarded with no body.

The proxy SHALL NOT impose a request body size ceiling of its own. Each upstream
service remains the sole authority over the size it accepts, so that services
with deliberately different limits — the agent-orchestrator's
`MAX_REQUEST_BODY_BYTES` and history-service's much larger
`HISTORY_IMPORT_MAX_BYTES` — keep those limits rather than sharing one number
chosen by the proxy.

So that an upstream can still refuse an oversized upload before reading it, the
proxy SHALL forward a well-formed declared request `Content-Length` on the
outbound request, and SHALL forward no `Content-Length` when the incoming value is
absent or not a plain number.

#### Scenario: A large upload reaches the upstream while the client is still sending

- **WHEN** a client uploads a multi-megabyte body through the proxy in many chunks
- **THEN** the upstream service SHALL begin receiving bytes before the client has
  finished sending, and SHALL receive the body in multiple chunks rather than as
  one complete payload

#### Scenario: A large response reaches the client while the upstream is still sending

- **WHEN** an upstream service streams a multi-megabyte or slowly produced response
  through the proxy
- **THEN** the proxy SHALL return the response before its body has finished
  arriving, and the client SHALL receive the body in multiple chunks as the
  upstream produces them

#### Scenario: A bodyless method is forwarded without a body

- **WHEN** a `GET`, `HEAD`, or bodyless `DELETE` request is proxied
- **THEN** the outbound request SHALL carry no body and no `duplex` declaration,
  and the upstream SHALL receive zero body bytes

#### Scenario: An upstream refuses an oversized body on its declared size

- **WHEN** a client sends a body whose declared `Content-Length` exceeds the target
  service's own configured limit
- **THEN** the upstream SHALL receive that declared length and SHALL be able to
  answer `413` without reading the body
- **AND** the proxy SHALL return that `413` and the upstream's own message to the
  client

#### Scenario: A chunked upload carries no declared length

- **WHEN** a client uploads a body with no `Content-Length`
- **THEN** the proxy SHALL forward the body without inventing a length, and the
  target service's own byte-counting limit SHALL remain the ceiling that applies

### Requirement: The service proxy forwards only end-to-end request headers

The dashboard's shared service proxy route SHALL remove every hop-by-hop header
from a proxied request before forwarding it: `connection`, `keep-alive`,
`proxy-authenticate`, `proxy-authorization`, `te`, `trailer`,
`transfer-encoding`, and `upgrade`, together with `content-length`,
`proxy-connection`, and `expect`. These describe the browser-to-dashboard hop, and
the framing of the dashboard-to-upstream hop is decided by the outbound request
rather than inherited from the incoming one.

Removing `transfer-encoding` is required for correctness as well as safety: Node's
`fetch` refuses to send a request carrying that header, so forwarding it fails
every chunked upload outright, and a proxy that lets two hops disagree about where
a body ends is what a request-smuggling attempt depends on.

The proxy SHALL also remove the browser's ambient credentials (`cookie`,
`authorization`) and all `x-forwarded-*` headers, and SHALL NOT forward the
dashboard's own `host`. It SHALL forward every other request header unchanged,
including `content-type`.

#### Scenario: A chunked upload is forwarded successfully

- **WHEN** a client uploads a body with `Transfer-Encoding: chunked` and no
  `Content-Length`
- **THEN** the proxy SHALL NOT forward the `transfer-encoding` header, and the
  upstream SHALL receive the complete body

#### Scenario: Hop-by-hop and credential headers do not reach the upstream

- **WHEN** a proxied request carries `cookie`, `authorization`, `x-forwarded-for`,
  `x-forwarded-host`, `keep-alive`, `proxy-connection`, `te`, `trailer`,
  `upgrade`, or `expect`
- **THEN** the upstream SHALL receive none of them, SHALL receive the request's
  `content-type` unchanged, and SHALL see its own host rather than the
  dashboard's

### Requirement: The service proxy rejects unsafe path segments before contacting an upstream

The dashboard's shared service proxy route SHALL reject a proxied path whose
segment is, or percent-decodes to, `.` or `..`, and SHALL also reject a segment
whose percent-decoded form contains a path separator (`/` or `\`) or that fails to
percent-decode at all. Rejection SHALL answer `400` with a message naming the
offending segment, and SHALL happen before any upstream connection is opened.

A segment such as `..%2fadmin` is neither `.` nor `..` yet decodes to `../admin`;
refusing it keeps the traversal guarantee inside this check rather than resting on
the outbound URL encoder re-encoding the separator. A segment that merely contains
a dot, such as `openapi.json`, SHALL still be accepted.

#### Scenario: A segment decoding to a path is refused

- **WHEN** a proxied path contains a segment that percent-decodes to something
  containing `/` or `\`, such as `..%2fadmin` or `%2e%2e%2f%2e%2e`
- **THEN** the proxy SHALL answer `400` naming the segment, and no upstream
  service SHALL receive a request

#### Scenario: An ordinary segment containing a dot is accepted

- **WHEN** a proxied path contains a segment such as `openapi.json`
- **THEN** the proxy SHALL forward it to the target service unchanged

### Requirement: Proxy security checks apply to streamed requests

The dashboard's shared service proxy route SHALL apply its cross-site check, its
service-name check, and its path-segment check **before** forwarding anything, so
that a rejected request opens no upstream connection and sends it no body bytes,
however large the body is.

The proxy SHALL apply its response header filter to a streamed response, dropping
`content-encoding`, `content-length`, and `transfer-encoding` — which describe the
upstream hop — while forwarding every other upstream header, including
`content-disposition`, so that a streamed download keeps its filename.

#### Scenario: A cross-site upload is rejected without reaching the upstream

- **WHEN** a request carrying a body arrives with `Sec-Fetch-Site: cross-site`, or
  with an `Origin` whose host differs from the request host and no
  `Sec-Fetch-Site`
- **THEN** the proxy SHALL answer `403` and no upstream service SHALL receive a
  request or any body bytes

#### Scenario: An unknown service name is rejected without reaching any upstream

- **WHEN** a proxied request names a service the dashboard does not configure
- **THEN** the proxy SHALL answer `404` and no upstream service SHALL receive a
  request

#### Scenario: A streamed download keeps its filename and loses upstream framing headers

- **WHEN** an upstream answers a proxied request with `content-disposition`,
  `content-encoding`, `content-length`, and `transfer-encoding`
- **THEN** the proxy's response SHALL carry the `content-disposition` unchanged and
  SHALL carry none of the three framing headers
