import { buildMergedOpenApi } from "@/features/swagger/lib/openapi";

export async function GET() {
  const result = await buildMergedOpenApi();
  return Response.json(result.document);
}

export async function HEAD() {
  return new Response(null, { status: 200 });
}
