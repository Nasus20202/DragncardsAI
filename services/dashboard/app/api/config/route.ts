import { getPublicConfig } from "@/features/config/lib/dashboard-config";

export async function GET() {
  return Response.json({ config: getPublicConfig() });
}
