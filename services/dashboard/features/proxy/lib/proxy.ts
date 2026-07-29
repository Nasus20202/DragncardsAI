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
    decoded === ".."
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
//   - cookie / authorization: the upstreams run inside the trusted network and
//     don't authenticate via the browser's ambient credentials. Forwarding them
//     would let a confused-deputy request carry a user's session.
//   - x-forwarded-*: spoofable client-supplied forwarding metadata.
const STRIPPED_REQUEST_HEADERS = new Set([
  "connection",
  "content-length",
  "host",
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
