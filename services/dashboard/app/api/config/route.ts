import { getPublicConfig } from "@/features/config/lib/dashboard-config";
import { createServerLogger } from "@/features/observability/lib/server-logging";
import { withServerSpan } from "@/features/observability/lib/server-tracing";

const logger = createServerLogger("dashboard.api.config");

export async function GET() {
  const result = await withServerSpan(
    "dashboard.config.public",
    { "config.scope": "public" },
    async () => getPublicConfig()
  );

  logger.info("dashboard config served public", {
    "config.scope": "public",
  });

  return Response.json({ config: result });
}
