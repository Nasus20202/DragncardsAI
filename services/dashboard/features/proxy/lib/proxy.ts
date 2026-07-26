import { getServerConfig } from "@/features/config/lib/dashboard-config";

export type ServiceKey = "orchestrator" | "game" | "history" | "eval";

const SERVICE_NAMES: Record<ServiceKey, string> = {
  orchestrator: "agent-orchestrator",
  game: "game-service",
  history: "history-service",
  eval: "eval-service",
};

export function isServiceKey(value: string): value is ServiceKey {
  return (
    value === "orchestrator" ||
    value === "game" ||
    value === "history" ||
    value === "eval"
  );
}

export function getServiceLabel(service: ServiceKey): string {
  return SERVICE_NAMES[service];
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
  const config = getServerConfig();
  const baseUrl =
    service === "orchestrator"
      ? config.orchestratorUrl
      : service === "history"
        ? config.historyServiceUrl
        : service === "eval"
          ? config.evalServiceUrl
          : config.gameServiceUrl;
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
