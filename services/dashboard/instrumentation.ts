import { registerOTel } from "@vercel/otel";

import { createLogRecordProcessors } from "./features/observability/lib/server-logging";
import {
  SERVICE_KEYS,
  getServiceBaseUrl,
  getServiceLabel,
} from "./features/proxy/lib/proxy";

function splitCsv(raw: string | undefined): string[] {
  if (!raw) {
    return [];
  }

  return raw
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

/**
 * Every first-party backend the dashboard calls server-side, by Docker service
 * name and by the host of its configured base URL (`localhost:400x` for a direct
 * local run).
 *
 * Trace context is only propagated to a URL that matches one of these, so a
 * backend missing from this list produces a SEPARATE trace instead of a child
 * span — the dashboard's half and the service's half never join up (DRA-23).
 * Derived from `SERVICE_KEYS` so a service added to that one declaration is
 * covered here without a second list to remember.
 */
function firstPartyBackends(): string[] {
  return SERVICE_KEYS.flatMap((service) => [
    getServiceLabel(service),
    new URL(getServiceBaseUrl(service)).host,
  ]);
}

export function propagateContextUrls(
  raw: string | undefined = process.env.OTEL_PROPAGATE_CONTEXT_URLS
): string[] {
  return splitCsv(raw).concat(firstPartyBackends());
}

export function register() {
  if (process.env.OTEL_SDK_DISABLED === "true") {
    return;
  }

  const logRecordProcessors = createLogRecordProcessors();

  registerOTel({
    serviceName: process.env.OTEL_SERVICE_NAME ?? "dashboard",
    ...(logRecordProcessors.length > 0 ? { logRecordProcessors } : {}),
    instrumentationConfig: {
      fetch: {
        propagateContextUrls: propagateContextUrls(),
      },
    },
  });
}
