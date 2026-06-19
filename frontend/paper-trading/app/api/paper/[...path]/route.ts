import { NextResponse } from "next/server";

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxy(request: Request, context: RouteContext) {
  const baseUrl = process.env.PAPER_TRADING_API_BASE_URL;
  const token = process.env.PAPER_TRADING_API_TOKEN;
  if (!baseUrl || !token) {
    return NextResponse.json(
      { code: "FRONTEND_CONFIG_ERROR", message: "Paper trading API configuration is missing" },
      { status: 500 }
    );
  }

  const { path } = await context.params;
  const incomingUrl = new URL(request.url);
  const targetUrl = new URL(`/paper/${path.join("/")}${incomingUrl.search}`, baseUrl);
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : request.body;

  try {
    const headers = new Headers({ authorization: `Bearer ${token}` });
    if (body) {
      headers.set("content-type", request.headers.get("content-type") ?? "application/json");
    }
    const init: RequestInit & { duplex?: "half" } = {
      method: request.method,
      headers,
      body
    };
    if (body) {
      init.duplex = "half";
    }
    const response = await fetch(targetUrl.toString(), init);
    const text = await response.text();
    return new Response(response.status === 204 ? null : text, {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json" }
    });
  } catch {
    return NextResponse.json({ code: "BACKEND_UNAVAILABLE", message: "Paper trading backend is unavailable" }, { status: 502 });
  }
}

export function GET(request: Request, context: RouteContext) {
  return proxy(request, context);
}

export function POST(request: Request, context: RouteContext) {
  return proxy(request, context);
}

export function DELETE(request: Request, context: RouteContext) {
  return proxy(request, context);
}
