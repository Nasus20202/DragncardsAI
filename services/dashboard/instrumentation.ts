import { registerOTel } from "@vercel/otel";

import { createLogRecordProcessors } from "./features/observability/lib/server-logging";

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
 * name and by the host port a direct local run uses.
 *
 * Trace context is only propagated to a URL that matches one of these, so a
 * backend missing from this list produces a SEPARATE trace instead of a child
 * span — the dashboard's half and the service's half never join up. Add a new
 * service here at the same time as its `*_SERVICE_URL` environment variable.
 */
const FIRST_PARTY_BACKENDS = [
  "agent-orchestrator",
  "game-service",
  "history-service",
  "eval-service",
  "localhost:4001",
  "localhost:4002",
  "localhost:4004",
  "localhost:4005",
];

export function propagateContextUrls(
  raw: string | undefined = process.env.OTEL_PROPAGATE_CONTEXT_URLS
): string[] {
  return splitCsv(raw).concat(FIRST_PARTY_BACKENDS);
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
