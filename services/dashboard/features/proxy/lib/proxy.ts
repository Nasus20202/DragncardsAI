import { getServerConfig } from "@/features/config/lib/dashboard-config";

/**
 * The single declaration of which first-party services the dashboard fronts.
 * Everything per-service — the proxy route's accepted segments, the upstream base
 * URLs, trace-context propagation, and the merged Swagger index — is a loop over
 * this array or a `Record<ServiceKey, …>`, so adding a service is one edit here
 * plus the type errors that follow. Never write a second list of service names
 * beside it: a partial list is how `history` and `eval` were reachable through
 * the proxy while being absent from the Swagger index (DRA-20).
 */
export const SERVICE_KEYS = [
  "orchestrator",
  "game",
  "history",
  "eval",
] as const;

export type ServiceKey = (typeof SERVICE_KEYS)[number];

const SERVICE_NAMES: Record<ServiceKey, string> = {
  orchestrator: "agent-orchestrator",
  game: "game-service",
  history: "history-service",
  eval: "eval-service",
};

export function isServiceKey(value: string): value is ServiceKey {
  return (SERVICE_KEYS as readonly string[]).includes(value);
}

export function getServiceLabel(service: ServiceKey): string {
  return SERVICE_NAMES[service];
}

/** The configured upstream base URL for a service. */
export function getServiceBaseUrl(service: ServiceKey): string {
  const config = getServerConfig();
  const baseUrls: Record<ServiceKey, string> = {
    orchestrator: config.orchestratorUrl,
    game: config.gameServiceUrl,
    history: config.historyServiceUrl,
    eval: config.evalServiceUrl,
  };

  return baseUrls[service];
}

/**
 * The path prefix a service's endpoints carry in the merged OpenAPI document:
 * the `[service]` segment of the `/api/proxy/[service]/[...path]` route.
 */
export function getServiceProxyPrefix(service: ServiceKey): string {
  return `/${service}`;
}

/** Thrown when a proxy path segment is invalid (e.g. path traversal). */
export class ProxyPathError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ProxyPathError";
  }
}

// Reject any segment that is, or percent-decodes to, "." or ".." so that
// traversal attempts (including encoded "%2e%2e") can never reach upstream
// paths the caller was not authorized for.
//
// A segment must also not percent-decode to something containing a path
// separator. `..%2fadmin` is a single segment that is neither "." nor "..", so
// the exact-match check alone lets it through, and it decodes to "../admin". It
// cannot actually traverse — `encodeURIComponent` re-encodes the slash, so the
// wire carries one opaque segment — but that safety rests entirely on the
// encoder, and a segment carrying a separator is never something a proxy caller
// legitimately needs. Refusing it keeps the guarantee in this function instead of
// in a downstream side effect.
function assertSafeSegment(segment: string): void {
  let decoded: string;
  try {
    decoded = decodeURIComponent(segment);
  } catch {
    throw new ProxyPathError(`Invalid proxy path segment: ${segment}`);
  }
  if (
    segment === "." ||
    segment === ".." ||
    decoded === "." ||
    decoded === ".." ||
    decoded.includes("/") ||
    decoded.includes("\\")
  ) {
    throw new ProxyPathError(`Invalid proxy path segment: ${segment}`);
  }
}

export function resolveProxyUrl(
  service: ServiceKey,
  pathSegments: string[],
  search: string
): URL {
  const baseUrl = getServiceBaseUrl(service);
  const normalizedPath = pathSegments
    .map((segment) => {
      assertSafeSegment(segment);
      return encodeURIComponent(segment);
    })
    .join("/");
  const target = new URL(baseUrl);
  const basePath = target.pathname.replace(/\/$/, "");

  target.pathname = `${basePath}/${normalizedPath}`.replace(/\/+/g, "/");
  target.search = search;
  return target;
}

// Hop-by-hop headers plus browser credentials / forwarding metadata that the
// trusted upstreams neither need nor should be allowed to trust from a browser:
//   - the RFC 9110 hop-by-hop set (connection, keep-alive, proxy-authenticate,
//     proxy-authorization, te, trailer, transfer-encoding, upgrade), plus
//     content-length and the non-standard proxy-connection. These describe the
//     browser-to-dashboard hop and say nothing about the dashboard-to-upstream
//     one, whose framing Node's fetch decides for itself. `transfer-encoding` in
//     particular must go: forwarding it makes Node's fetch reject the call
//     outright ("invalid transfer-encoding header"), which broke every chunked
//     upload, and two hops disagreeing about where a body ends is exactly what a
//     request-smuggling attempt needs.
//   - expect: a `100-continue` handshake belongs to the hop that negotiated it.
//   - cookie / authorization: the upstreams run inside the trusted network and
//     don't authenticate via the browser's ambient credentials. Forwarding them
//     would let a confused-deputy request carry a user's session.
//   - x-forwarded-*: spoofable client-supplied forwarding metadata.
const STRIPPED_REQUEST_HEADERS = new Set([
  "connection",
  "content-length",
  "expect",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "proxy-connection",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "cookie",
  "authorization",
]);

export function filterProxyRequestHeaders(headers: Headers): Headers {
  const filtered = new Headers();

  headers.forEach((value, key) => {
    const lowerKey = key.toLowerCase();
    if (STRIPPED_REQUEST_HEADERS.has(lowerKey)) {
      return;
    }
    if (lowerKey.startsWith("x-forwarded-")) {
      return;
    }
    filtered.set(key, value);
  });

  return filtered;
}

/**
 * `RequestInit` plus the `duplex` field. `duplex: "half"` is mandatory in
 * Node's `fetch` (undici) whenever `body` is a `ReadableStream` — without it the
 * call throws `RequestInit: duplex option is required when sending a body`
 * before a byte leaves the process. The DOM `RequestInit` that
 * `tsconfig.json`'s `lib: ["dom"]` provides has no `duplex` member, so it is
 * declared here rather than cast away at the call site.
 */
export type ProxyRequestInit = RequestInit & { duplex?: "half" };

// Methods whose bodies are forwarded as-is. A `GET`/`HEAD` body is not
// meaningful and Node's fetch rejects one outright, so those two keep sending
// no body at all — the behaviour the route has always had.
const BODYLESS_METHODS = new Set(["GET", "HEAD"]);

/**
 * Build the outbound `fetch` init for a proxied request.
 *
 * The incoming body is forwarded as the **stream Next.js handed us** rather than
 * read into an `ArrayBuffer` first. Buffering would make the dashboard process
 * hold a whole upload — a lossless history bundle embeds a full DragnCards board
 * state per event, so a real game's export runs to tens of megabytes — and it
 * would defeat the upstreams that are careful to stream: history-service's
 * import reader validates and writes line by line, and would instead be handed a
 * body the proxy had already materialized in full.
 *
 * The proxy deliberately imposes **no size ceiling of its own**. Each upstream
 * enforces its own, and they differ on purpose: the agent-orchestrator's
 * `MAX_REQUEST_BODY_BYTES` (8 MiB, counted by its ASGI `MaxBodySizeMiddleware`)
 * and history-service's `HISTORY_IMPORT_MAX_BYTES` (64 MiB, counted by its
 * streaming `BundleReader`). Both count bytes as they arrive, so streaming
 * through the proxy leaves both fully enforced; a cap in the shared proxy would
 * have to pick one number and would flatten that distinction.
 *
 * What those upstreams *also* do is reject an oversized upload on its declared
 * `Content-Length` before reading a byte. `filterProxyRequestHeaders` strips
 * `content-length` as hop-by-hop, and a streamed body makes Node's fetch fall
 * back to `Transfer-Encoding: chunked`, which would silently retire that fast
 * rejection. So a well-formed declared length is re-attached here: HTTP/1.1
 * framing means the incoming stream yields exactly that many bytes, and Node's
 * fetch honours an explicit `content-length` alongside a stream body instead of
 * chunking. A missing or non-numeric value is simply not forwarded, and the
 * upstreams' byte counting covers that case as it always has.
 */
export function buildProxyRequestInit(request: Request): ProxyRequestInit {
  const headers = filterProxyRequestHeaders(request.headers);
  const shared = {
    method: request.method,
    headers,
    cache: "no-store",
    redirect: "manual",
  } as const satisfies ProxyRequestInit;

  if (BODYLESS_METHODS.has(request.method.toUpperCase()) || !request.body) {
    return shared;
  }

  const declaredLength = request.headers.get("content-length");
  if (declaredLength !== null && /^\d+$/.test(declaredLength)) {
    headers.set("content-length", declaredLength);
  }

  return { ...shared, body: request.body, duplex: "half" };
}

/**
 * Cross-site defense-in-depth for the proxy. Browsers attach `Sec-Fetch-Site`
 * to fetches; we accept `same-origin` and `none` (top-level navigations /
 * direct address-bar requests) and reject `cross-site` / `same-site`. When the
 * header is absent (server-to-server callers, older agents) we fall back to
 * comparing the `Origin` host against the request host. Requests with neither
 * signal are allowed so normal same-origin/server usage is never broken.
 */
export function isCrossSiteRequest(request: Request): boolean {
  const secFetchSite = request.headers.get("sec-fetch-site");
  if (secFetchSite) {
    return secFetchSite !== "same-origin" && secFetchSite !== "none";
  }

  const origin = request.headers.get("origin");
  if (origin) {
    let originHost: string;
    try {
      originHost = new URL(origin).host;
    } catch {
      // An unparseable Origin can't be proven same-origin; reject it.
      return true;
    }
    return originHost !== new URL(request.url).host;
  }

  return false;
}

export function filterProxyResponseHeaders(headers: Headers): Headers {
  const filtered = new Headers();

  headers.forEach((value, key) => {
    const lowerKey = key.toLowerCase();
    if (
      ["content-encoding", "content-length", "transfer-encoding"].includes(
        lowerKey
      )
    ) {
      return;
    }
    filtered.set(key, value);
  });

  return filtered;
}
