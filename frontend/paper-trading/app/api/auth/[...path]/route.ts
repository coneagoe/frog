import { NextResponse } from "next/server";

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxy(request: Request, context: RouteContext) {
  const baseUrl = process.env.PAPER_TRADING_API_BASE_URL;
  if (!baseUrl) {
    return NextResponse.json(
      { code: "FRONTEND_CONFIG_ERROR", message: "Paper trading API configuration is missing" },
      { status: 500 }
    );
  }

  const { path } = await context.params;
  const incomingUrl = new URL(request.url);
  const targetUrl = new URL(`/auth/${path.join("/")}${incomingUrl.search}`, baseUrl);
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : request.body;

  try {
    const headers = new Headers();
    for (const name of ["cookie", "content-type", "x-csrf-token"]) {
      const value = request.headers.get(name);
      if (value) headers.set(name, value);
    }
    const init: RequestInit & { duplex?: "half" } = { method: request.method, headers, body, credentials: "include" };
    if (body) init.duplex = "half";
    const response = await fetch(targetUrl.toString(), init);
    const responseHeaders = new Headers();
    const contentType = response.headers.get("content-type");
    if (contentType) responseHeaders.set("content-type", contentType);
    for (const setCookie of response.headers.getSetCookie()) {
      responseHeaders.append("set-cookie", setCookie);
    }
    const text = await response.text();
    return new Response(response.status === 204 ? null : text, { status: response.status, headers: responseHeaders });
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
