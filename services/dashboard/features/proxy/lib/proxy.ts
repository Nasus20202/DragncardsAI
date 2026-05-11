import { getServerConfig } from "@/features/config/lib/dashboard-config";

export type ServiceKey = "orchestrator" | "game";

const SERVICE_NAMES: Record<ServiceKey, string> = {
  orchestrator: "agent-orchestrator",
  game: "game-service",
};

export function isServiceKey(value: string): value is ServiceKey {
  return value === "orchestrator" || value === "game";
}

export function getServiceLabel(service: ServiceKey): string {
  return SERVICE_NAMES[service];
}

export function resolveProxyUrl(
  service: ServiceKey,
  pathSegments: string[],
  search: string
): URL {
  const config = getServerConfig();
  const baseUrl =
    service === "orchestrator" ? config.orchestratorUrl : config.gameServiceUrl;
  const normalizedPath = pathSegments
    .map((segment) => encodeURIComponent(segment))
    .join("/");
  const target = new URL(baseUrl);
  const basePath = target.pathname.replace(/\/$/, "");

  target.pathname = `${basePath}/${normalizedPath}`.replace(/\/+/g, "/");
  target.search = search;
  return target;
}

export function filterProxyRequestHeaders(headers: Headers): Headers {
  const filtered = new Headers();

  headers.forEach((value, key) => {
    const lowerKey = key.toLowerCase();
    if (["connection", "content-length", "host"].includes(lowerKey)) {
      return;
    }
    filtered.set(key, value);
  });

  return filtered;
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
