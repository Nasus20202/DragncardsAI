import {
  filterProxyRequestHeaders,
  filterProxyResponseHeaders,
  isServiceKey,
  resolveProxyUrl,
  type ServiceKey,
} from "@/features/proxy/lib/proxy";
import { createServerLogger } from "@/features/observability/lib/server-logging";
import { withServerSpan } from "@/features/observability/lib/server-tracing";

const logger = createServerLogger("dashboard.api.proxy");

function formatProxyPath(path: string[]): string {
  return path.length > 0 ? path.join("/") : "<root>";
}

type RouteContext = {
  params: Promise<{
    service: string;
    path: string[];
  }>;
};

async function proxyRequest(request: Request, context: RouteContext) {
  const { service, path } = await context.params;
  const proxyPath = formatProxyPath(path);

  if (!isServiceKey(service)) {
    logger.warn(
      `dashboard proxy ${request.method} ${service}/${proxyPath} rejected`,
      {
        "proxy.service": service,
        "proxy.path": proxyPath,
        "http.request.method": request.method,
        "http.response.status_code": 404,
        "error.type": "unknown_service",
      }
    );

    return Response.json(
      { detail: `Unknown proxy service ${service}` },
      { status: 404 }
    );
  }

  const serviceKey: ServiceKey = service;

  async function proxyUpstream() {
    const incomingUrl = new URL(request.url);
    const targetUrl = resolveProxyUrl(serviceKey, path, incomingUrl.search);
    const body =
      request.method === "GET" || request.method === "HEAD"
        ? undefined
        : await request.arrayBuffer();

    try {
      const upstreamResponse = await fetch(targetUrl, {
        method: request.method,
        headers: filterProxyRequestHeaders(request.headers),
        body,
        cache: "no-store",
        redirect: "manual",
      });

      logger.info(
        `dashboard proxy ${request.method} ${serviceKey}/${proxyPath} -> ${upstreamResponse.status}`,
        {
          "proxy.service": serviceKey,
          "proxy.target": targetUrl.toString(),
          "proxy.path": proxyPath,
          "http.request.method": request.method,
          "http.response.status_code": upstreamResponse.status,
        }
      );

      return new Response(upstreamResponse.body, {
        status: upstreamResponse.status,
        statusText: upstreamResponse.statusText,
        headers: filterProxyResponseHeaders(upstreamResponse.headers),
      });
    } catch (error) {
      logger.error(
        `dashboard proxy ${request.method} ${serviceKey}/${proxyPath} failed`,
        {
          "proxy.service": serviceKey,
          "proxy.target": targetUrl.toString(),
          "proxy.path": proxyPath,
          "http.request.method": request.method,
          "error.name": error instanceof Error ? error.name : undefined,
          "error.message":
            error instanceof Error ? error.message : String(error),
        }
      );

      throw error;
    }
  }

  return withServerSpan(
    "dashboard.proxy_request",
    {
      "proxy.service": serviceKey,
      "http.request.method": request.method,
      "proxy.path": path.join("/"),
    },
    proxyUpstream
  );
}

export async function GET(request: Request, context: RouteContext) {
  return proxyRequest(request, context);
}

export async function POST(request: Request, context: RouteContext) {
  return proxyRequest(request, context);
}

export async function PUT(request: Request, context: RouteContext) {
  return proxyRequest(request, context);
}

export async function PATCH(request: Request, context: RouteContext) {
  return proxyRequest(request, context);
}

export async function DELETE(request: Request, context: RouteContext) {
  return proxyRequest(request, context);
}
