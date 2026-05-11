import { registerOTel } from "@vercel/otel";

function splitCsv(raw: string | undefined): string[] {
  if (!raw) {
    return [];
  }

  return raw
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function register() {
  if (process.env.OTEL_SDK_DISABLED === "true") {
    return;
  }

  registerOTel({
    serviceName: process.env.OTEL_SERVICE_NAME ?? "dashboard",
    instrumentationConfig: {
      fetch: {
        propagateContextUrls: splitCsv(
          process.env.OTEL_PROPAGATE_CONTEXT_URLS
        ).concat([
          "agent-orchestrator",
          "game-service",
          "localhost:4001",
          "localhost:4002",
        ]),
      },
    },
  });
}
