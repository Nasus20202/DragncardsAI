import {
  filterProxyRequestHeaders,
  filterProxyResponseHeaders,
  isServiceKey,
  resolveProxyUrl,
  type ServiceKey,
} from "@/features/proxy/lib/proxy";
import { withServerSpan } from "@/features/observability/lib/server-tracing";

type RouteContext = {
  params: Promise<{
    service: string;
    path: string[];
  }>;
};

async function proxyRequest(request: Request, context: RouteContext) {
  const { service, path } = await context.params;

  if (!isServiceKey(service)) {
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

    const upstreamResponse = await fetch(targetUrl, {
      method: request.method,
      headers: filterProxyRequestHeaders(request.headers),
      body,
      cache: "no-store",
      redirect: "manual",
    });

    return new Response(upstreamResponse.body, {
      status: upstreamResponse.status,
      statusText: upstreamResponse.statusText,
      headers: filterProxyResponseHeaders(upstreamResponse.headers),
    });
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
