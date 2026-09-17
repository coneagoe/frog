import { NextResponse } from "next/server";

type RouteContext = { params: Promise<{ path: string[] }> };
const UNAVAILABLE = { code: "AUTH_UNAVAILABLE", message: "登录服务暂时不可用，请稍后重试。" };
function bodyCode(text: string) { try { const payload = JSON.parse(text); return payload.detail?.code ?? payload.code; } catch { return undefined; } }

function unavailable(requestId: string, requestPath: string) {
  console.info(JSON.stringify({ event_code: "AUTH_PROXY_MISROUTED", outcome: "unavailable", http_status: 503, request_id: requestId, request_path: requestPath }));
  return NextResponse.json({ ...UNAVAILABLE, request_id: requestId }, { status: 503, headers: { "X-Request-ID": requestId } });
}

async function proxy(request: Request, context: RouteContext) {
  const requestId = crypto.randomUUID();
  const { path } = await context.params;
  const isLogin = path.join("/") === "login";
  const baseUrl = process.env.PAPER_TRADING_API_BASE_URL;
  if (!baseUrl) {
    return unavailable(requestId, "/auth");
  }

  try {
    const incomingUrl = new URL(request.url);
    const targetUrl = new URL(`/auth/${path.join("/")}${incomingUrl.search}`, baseUrl);
    const body = request.method === "GET" || request.method === "HEAD" ? undefined : request.body;
    const headers = new Headers();
    for (const name of ["cookie", "content-type", "x-csrf-token"]) {
      const value = request.headers.get(name);
      if (value) headers.set(name, value);
    }
    headers.set("X-Request-ID", requestId);
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
    const backendRequestId = response.headers.get("X-Request-ID");
    if (response.status === 503 && bodyCode(text) === "AUTH_UNAVAILABLE") {
      if (backendRequestId) responseHeaders.set("X-Request-ID", backendRequestId);
      return new Response(text, { status: 503, headers: responseHeaders });
    }
    if (response.status === 503) return unavailable(requestId, "/auth");
    if (response.status === 401 && isLogin) return new Response(text, { status: 401, headers: responseHeaders });
    if (backendRequestId) responseHeaders.set("X-Request-ID", backendRequestId);
    return new Response(response.status === 204 ? null : text, { status: response.status, headers: responseHeaders });
  } catch {
    return unavailable(requestId, "/auth");
  }
}

export function GET(request: Request, context: RouteContext) {
  return proxy(request, context);
}

export function POST(request: Request, context: RouteContext) {
  return proxy(request, context);
}
