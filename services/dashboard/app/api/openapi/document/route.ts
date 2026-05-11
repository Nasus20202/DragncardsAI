import { buildMergedOpenApi } from "@/features/swagger/lib/openapi";
import { createServerLogger } from "@/features/observability/lib/server-logging";
import { withServerSpan } from "@/features/observability/lib/server-tracing";

const logger = createServerLogger("dashboard.api.openapi.document");

export async function GET() {
  const result = await withServerSpan(
    "dashboard.openapi.document",
    { "openapi.document": "public" },
    async () => buildMergedOpenApi()
  );

  logger.info(
    `dashboard openapi document served errors=${result.errors.length}`,
    {
      "openapi.document": "public",
      "openapi.error_count": result.errors.length,
    }
  );

  return Response.json(result.document);
}

export async function HEAD() {
  return new Response(null, { status: 200 });
}
