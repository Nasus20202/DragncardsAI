import { logs, SeverityNumber } from "@opentelemetry/api-logs";
import { OTLPLogExporter } from "@opentelemetry/exporter-logs-otlp-http";
import {
  BatchLogRecordProcessor,
  type LogRecordProcessor,
} from "@opentelemetry/sdk-logs";

type ServerLogLevel = "debug" | "error" | "info" | "warn";
type LogAttributes = Record<string, string | number | boolean | undefined>;

const SEVERITY_BY_LEVEL: Record<ServerLogLevel, SeverityNumber> = {
  debug: SeverityNumber.DEBUG,
  error: SeverityNumber.ERROR,
  info: SeverityNumber.INFO,
  warn: SeverityNumber.WARN,
};

function isNodeRuntime(): boolean {
  return (process.env.NEXT_RUNTIME ?? "nodejs") === "nodejs";
}

function filterAttributes(
  attributes: LogAttributes
): Record<string, string | number | boolean> {
  return Object.fromEntries(
    Object.entries(attributes).filter(([, value]) => value !== undefined)
  ) as Record<string, string | number | boolean>;
}

export function createLogRecordProcessors(): LogRecordProcessor[] {
  if (!isNodeRuntime()) {
    return [];
  }

  return [new BatchLogRecordProcessor(new OTLPLogExporter())];
}

export function createServerLogger(name = "dashboard.server") {
  const logger = logs.getLogger(name);

  function emit(
    level: ServerLogLevel,
    body: string,
    attributes: LogAttributes = {}
  ): void {
    if (!isNodeRuntime()) {
      return;
    }

    logger.emit({
      severityNumber: SEVERITY_BY_LEVEL[level],
      severityText: level.toUpperCase(),
      body,
      attributes: {
        "log.type": "app",
        ...filterAttributes(attributes),
      },
    });
  }

  return {
    debug(body: string, attributes?: LogAttributes) {
      emit("debug", body, attributes);
    },
    info(body: string, attributes?: LogAttributes) {
      emit("info", body, attributes);
    },
    warn(body: string, attributes?: LogAttributes) {
      emit("warn", body, attributes);
    },
    error(body: string, attributes?: LogAttributes) {
      emit("error", body, attributes);
    },
  };
}
