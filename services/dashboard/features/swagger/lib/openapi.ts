import { getServerConfig } from "@/features/config/lib/dashboard-config";
import { ServiceKey } from "@/features/proxy/lib/proxy";
import { MergedOpenApiResult, JsonValue } from "@/features/shared/lib/types";

const SERVICE_PREFIX: Record<ServiceKey, string> = {
  orchestrator: "/orchestrator",
  game: "/game",
  history: "/history",
  eval: "/eval",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function deepRewriteRefs(value: unknown, service: ServiceKey): JsonValue {
  if (Array.isArray(value)) {
    return value.map((item) => deepRewriteRefs(item, service));
  }

  if (typeof value === "string") {
    const match = value.match(/^#\/components\/([^/]+)\/(.+)$/);
    if (!match) {
      return value;
    }

    return `#/components/${match[1]}/${service}_${match[2]}`;
  }

  if (!isRecord(value)) {
    return (value ?? null) as JsonValue;
  }

  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [
      key,
      deepRewriteRefs(item, service),
    ])
  ) as JsonValue;
}

function namespaceComponents(
  components: Record<string, unknown> | undefined,
  service: ServiceKey
): Record<string, JsonValue> {
  if (!components) {
    return {};
  }

  return Object.fromEntries(
    Object.entries(components).map(([section, rawEntries]) => {
      if (!isRecord(rawEntries)) {
        return [section, {}];
      }

      return [
        section,
        Object.fromEntries(
          Object.entries(rawEntries).map(([name, definition]) => [
            `${service}_${name}`,
            deepRewriteRefs(definition, service),
          ])
        ),
      ];
    })
  ) as Record<string, JsonValue>;
}

function namespaceDocument(
  document: Record<string, unknown>,
  service: ServiceKey
) {
  const prefixedPaths = Object.fromEntries(
    Object.entries(
      (document.paths as Record<string, unknown> | undefined) ?? {}
    ).map(([path, pathItem]) => [
      `${SERVICE_PREFIX[service]}${path}`,
      deepRewriteRefs(pathItem, service),
    ])
  );

  const tags = Array.isArray(document.tags)
    ? document.tags.map((tag) => {
        if (!isRecord(tag)) {
          return tag as JsonValue;
        }

        return {
          ...tag,
          name: `${service}:${String(tag.name ?? "default")}`,
        } as JsonValue;
      })
    : [];

  for (const pathItem of Object.values(prefixedPaths)) {
    if (!isRecord(pathItem)) {
      continue;
    }

    for (const operation of Object.values(pathItem)) {
      if (!isRecord(operation)) {
        continue;
      }

      if (Array.isArray(operation.tags)) {
        operation.tags = operation.tags.map(
          (tag) => `${service}:${String(tag)}`
        );
      }
      if (typeof operation.operationId === "string") {
        operation.operationId = `${service}_${operation.operationId}`;
      }
    }
  }

  return {
    paths: prefixedPaths,
    tags,
    components: namespaceComponents(
      document.components as Record<string, unknown> | undefined,
      service
    ),
  };
}

async function fetchOpenApiDocument(
  service: ServiceKey,
  fetchImpl: typeof fetch
): Promise<Record<string, unknown>> {
  const config = getServerConfig();
  const target = new URL(
    service === "orchestrator"
      ? config.orchestratorOpenApiPath
      : config.gameServiceOpenApiPath,
    service === "orchestrator" ? config.orchestratorUrl : config.gameServiceUrl
  );
  const response = await fetchImpl(target, {
    headers: { accept: "application/json" },
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(
      `${service} OpenAPI request failed with status ${response.status}`
    );
  }

  const document = (await response.json()) as unknown;
  if (!isRecord(document)) {
    throw new Error(`${service} OpenAPI document is not an object`);
  }

  return document;
}

export async function buildMergedOpenApi(
  fetchImpl: typeof fetch = fetch
): Promise<MergedOpenApiResult> {
  const errors: { service: string; message: string }[] = [];
  const merged: Record<string, unknown> = {
    openapi: "3.1.0",
    info: {
      title: "DragnCardsAI Merged API",
      version: "0.1.0",
      description: "Merged OpenAPI surface for the dashboard playground.",
    },
    servers: [{ url: "/api/proxy" }],
    tags: [],
    paths: {},
    components: {},
  };

  for (const service of ["orchestrator", "game"] as const) {
    try {
      const document = await fetchOpenApiDocument(service, fetchImpl);
      const namespaced = namespaceDocument(document, service);
      Object.assign(merged.paths as Record<string, unknown>, namespaced.paths);
      Object.assign(merged.components as Record<string, unknown>, {
        ...(merged.components as Record<string, unknown>),
        ...Object.fromEntries(
          Object.entries(namespaced.components).map(([section, value]) => {
            const existing =
              (merged.components as Record<string, Record<string, unknown>>)[
                section
              ] ?? {};
            return [
              section,
              { ...existing, ...(value as Record<string, unknown>) },
            ];
          })
        ),
      });
      (merged.tags as JsonValue[]).push(...namespaced.tags);
    } catch (error) {
      errors.push({
        service,
        message:
          error instanceof Error
            ? error.message
            : "Unknown OpenAPI merge error",
      });
    }
  }

  return {
    document: {
      ...(merged as Record<string, JsonValue>),
      "x-dashboard-errors": errors,
    },
    errors,
  };
}
