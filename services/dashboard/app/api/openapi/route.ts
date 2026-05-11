import { buildMergedOpenApi } from "@/features/swagger/lib/openapi";
import { createServerLogger } from "@/features/observability/lib/server-logging";
import { withServerSpan } from "@/features/observability/lib/server-tracing";

const logger = createServerLogger("dashboard.api.openapi");

export async function GET() {
  const result = await withServerSpan(
    "dashboard.openapi.merge",
    { "openapi.document": "merged" },
    async () => buildMergedOpenApi()
  );

  logger.info(`dashboard openapi merged errors=${result.errors.length}`, {
    "openapi.document": "merged",
    "openapi.error_count": result.errors.length,
  });

  return Response.json(result);
}

export async function HEAD() {
  return new Response(null, { status: 200 });
}
