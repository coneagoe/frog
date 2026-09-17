import { NextResponse } from "next/server";

type RouteContext = { params: Promise<{ path: string[] }> };
const UNAVAILABLE = { code: "AUTH_UNAVAILABLE", message: "登录服务暂时不可用，请稍后重试。" };
function bodyCode(text: string | null) { try { const payload = JSON.parse(text ?? ""); return payload.detail?.code ?? payload.code; } catch { return undefined; } }

function unavailable(requestId: string, requestPath: string) {
  console.info(JSON.stringify({ event_code: "AUTH_PROXY_MISROUTED", outcome: "unavailable", http_status: 503, request_id: requestId, request_path: requestPath }));
  return NextResponse.json({ ...UNAVAILABLE, request_id: requestId }, { status: 503, headers: { "X-Request-ID": requestId } });
}

async function proxy(request: Request, context: RouteContext) {
  const requestId = crypto.randomUUID();
  const { path } = await context.params;
  const baseUrl = process.env.PAPER_TRADING_API_BASE_URL;
  if (!baseUrl) {
    return unavailable(requestId, "/paper");
  }

  try {
    const incomingUrl = new URL(request.url);
    const targetUrl = new URL(`/paper/${path.join("/")}${incomingUrl.search}`, baseUrl);
    const body = request.method === "GET" || request.method === "HEAD" ? undefined : request.body;
    const headers = new Headers();
    for (const header of ["cookie", "content-type", "x-csrf-token"]) {
      const value = request.headers.get(header);
      if (value) {
        headers.set(header, value);
      }
    }
    headers.set("X-Request-ID", requestId);
    const init: RequestInit & { duplex?: "half" } = {
      method: request.method,
      headers,
      body
    };
    if (body) {
      init.duplex = "half";
    }
    const response = await fetch(targetUrl.toString(), init);
    const responseHeaders = new Headers(response.headers);
    const text = response.status === 204 ? null : await response.text();
    if (response.status === 503) return bodyCode(text) === "AUTH_UNAVAILABLE" ? new Response(text, { status: 503, headers: responseHeaders }) : new Response(text, { status: 503, headers: responseHeaders });
    return new Response(text, {
      status: response.status,
      headers: responseHeaders
    });
  } catch {
    return unavailable(requestId, "/paper");
  }
}

export function GET(request: Request, context: RouteContext) {
  return proxy(request, context);
}

export function POST(request: Request, context: RouteContext) {
  return proxy(request, context);
}

export function PATCH(request: Request, context: RouteContext) {
  return proxy(request, context);
}

export function DELETE(request: Request, context: RouteContext) {
  return proxy(request, context);
}
