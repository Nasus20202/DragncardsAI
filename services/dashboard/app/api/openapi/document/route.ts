import { buildMergedOpenApi } from "@/features/swagger/lib/openapi";
import { withServerSpan } from "@/features/observability/lib/server-tracing";

export async function GET() {
  const result = await withServerSpan(
    "dashboard.openapi.document",
    { "openapi.document": "public" },
    async () => buildMergedOpenApi()
  );
  return Response.json(result.document);
}

export async function HEAD() {
  return new Response(null, { status: 200 });
}
