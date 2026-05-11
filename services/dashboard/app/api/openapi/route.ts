import { buildMergedOpenApi } from "@/features/swagger/lib/openapi";
import { withServerSpan } from "@/features/observability/lib/server-tracing";

export async function GET() {
  const result = await withServerSpan(
    "dashboard.openapi.merge",
    { "openapi.document": "merged" },
    async () => buildMergedOpenApi()
  );
  return Response.json(result);
}

export async function HEAD() {
  return new Response(null, { status: 200 });
}
