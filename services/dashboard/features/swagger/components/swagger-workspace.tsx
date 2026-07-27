"use client";

import { Alert, Card, Chip, Spinner } from "@heroui/react";
import { useEffect, useState } from "react";

interface OpenApiPayload {
  document: Record<string, unknown>;
  errors: { service: string; message: string }[];
}

export function SwaggerWorkspace() {
  const [payload, setPayload] = useState<OpenApiPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const response = await fetch("/api/openapi", { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`Failed to load merged OpenAPI: ${response.status}`);
        }
        setPayload((await response.json()) as OpenApiPayload);
      } catch (nextError) {
        setError(
          nextError instanceof Error
            ? nextError.message
            : "Failed to load OpenAPI"
        );
      }
    }

    void load();
  }, []);

  if (error) {
    return (
      <Alert status="danger" role="alert">
        {error}
      </Alert>
    );
  }

  if (!payload) {
    return (
      <div className="flex h-full items-center justify-center py-12">
        <div className="flex items-center gap-3 text-sm text-default-500">
          <Spinner size="sm" />
          Loading merged OpenAPI
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-[calc(100vh-6rem)] flex-col gap-3">
      <Card className="p-4 shadow-none">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Swagger playground</h2>
            <p className="text-sm text-default-500">
              Merged OpenAPI for DragncardsAI, executed through dashboard proxy
              routes.
            </p>
          </div>
          <Chip color="accent" variant="soft">
            /api/proxy
          </Chip>
        </div>
        {payload.errors.length > 0 ? (
          <Alert status="warning" role="status" className="mt-4">
            Partial OpenAPI load:
            <ul className="ml-5 mt-2 list-disc">
              {payload.errors.map((item) => (
                <li key={`${item.service}:${item.message}`}>
                  {item.service}: {item.message}
                </li>
              ))}
            </ul>
          </Alert>
        ) : null}
      </Card>

      <Card className="min-h-0 flex-1 overflow-hidden p-0 shadow-none">
        <div className="flex h-full min-h-[calc(100vh-12rem)] flex-col bg-white">
          <iframe
            className="h-full w-full border-0 bg-white"
            src="/swagger/embed"
            title="Swagger UI"
          />
        </div>
      </Card>
    </div>
  );
}
