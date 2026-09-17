import { afterEach, describe, expect, it, vi } from "vitest";
import { GET, POST } from "./route";

afterEach(() => {
  vi.restoreAllMocks();
  delete process.env.PAPER_TRADING_API_BASE_URL;
});

describe("auth proxy", () => {
  it("forwards browser cookies and CSRF without exposing the API token", async () => {
    process.env.PAPER_TRADING_API_BASE_URL = "http://backend.test";
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 1 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await POST(new Request("http://localhost/api/auth/logout", {
      method: "POST",
      headers: { cookie: "paper_trading_session=session; paper_trading_csrf=csrf", "x-csrf-token": "csrf", "content-type": "application/json" },
      body: JSON.stringify({})
    }), { params: Promise.resolve({ path: ["logout"] }) });

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledWith("http://backend.test/auth/logout", expect.objectContaining({ method: "POST", credentials: "include" }));
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get("cookie")).toContain("paper_trading_session=session");
    expect(headers.get("x-csrf-token")).toBe("csrf");
    expect(headers.has("authorization")).toBe(false);
  });

  it("preserves backend errors and session cookies", async () => {
    process.env.PAPER_TRADING_API_BASE_URL = "http://backend.test";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: "UNAUTHORIZED", message: "Unauthorized" }), {
      status: 401,
      headers: { "content-type": "application/json", "set-cookie": "paper_trading_session=token; HttpOnly" }
    })));

    const response = await GET(new Request("http://localhost/api/auth/me"), { params: Promise.resolve({ path: ["me"] }) });
    expect(response.status).toBe(401);
    expect(response.headers.get("set-cookie")).toContain("paper_trading_session=token");
    await expect(response.json()).resolves.toEqual({ code: "UNAUTHORIZED", message: "Unauthorized" });
  });

  it("preserves both cookies from a login response", async () => {
    process.env.PAPER_TRADING_API_BASE_URL = "http://backend.test";
    const backendResponse = new Response(JSON.stringify({ id: 1 }), { status: 200 });
    backendResponse.headers.append("set-cookie", "paper_trading_session=session-token; HttpOnly; SameSite=Lax");
    backendResponse.headers.append("set-cookie", "paper_trading_csrf=csrf-token; SameSite=Lax");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(backendResponse));

    const response = await POST(new Request("http://localhost/api/auth/login", { method: "POST" }), {
      params: Promise.resolve({ path: ["login"] })
    });

    const cookies = response.headers.getSetCookie();
    expect(cookies).toHaveLength(2);
    expect(cookies).toEqual(expect.arrayContaining([
      "paper_trading_session=session-token; HttpOnly; SameSite=Lax",
      "paper_trading_csrf=csrf-token; SameSite=Lax"
    ]));
  });

  it("generates and forwards one server request ID, ignoring the client value", async () => {
    process.env.PAPER_TRADING_API_BASE_URL = "http://backend.test";
    vi.stubGlobal("crypto", { randomUUID: vi.fn().mockReturnValue("11111111-1111-4111-8111-111111111111") });
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(new Request("http://localhost/api/auth/me", { headers: { "x-request-id": "client-id" } }), {
      params: Promise.resolve({ path: ["me"] })
    });

    expect(response.headers.get("x-request-id")).toBeNull();
    expect((fetchMock.mock.calls[0][1].headers as Headers).get("x-request-id")).toBe("11111111-1111-4111-8111-111111111111");
  });

  it("normalizes configuration and backend-unavailable failures with evidence", async () => {
    vi.stubGlobal("crypto", { randomUUID: vi.fn().mockReturnValue("22222222-2222-4222-8222-222222222222") });
    const missingConfig = await GET(new Request("http://localhost/api/auth/me"), { params: Promise.resolve({ path: ["me"] }) });
    await expect(missingConfig.json()).resolves.toEqual({ code: "AUTH_UNAVAILABLE", message: "登录服务暂时不可用，请稍后重试。", request_id: "22222222-2222-4222-8222-222222222222" });
    expect(missingConfig.status).toBe(503);
    expect(missingConfig.headers.get("x-request-id")).toBe("22222222-2222-4222-8222-222222222222");

    process.env.PAPER_TRADING_API_BASE_URL = "http://backend.test";
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
    const unavailable = await GET(new Request("http://localhost/api/auth/me"), { params: Promise.resolve({ path: ["me"] }) });
    expect(unavailable.status).toBe(503);
    const unavailableBody = await unavailable.json();
    expect(unavailableBody).toMatchObject({ code: "AUTH_UNAVAILABLE", request_id: expect.any(String) });
    expect(unavailable.headers.get("x-request-id")).toBe(unavailableBody.request_id);
  });

  it("clears cookies only for an explicit session-invalid response", async () => {
    process.env.PAPER_TRADING_API_BASE_URL = "http://backend.test";
    vi.stubGlobal("crypto", { randomUUID: vi.fn().mockReturnValue("33333333-3333-4333-8333-333333333333") });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { code: "SESSION_INVALID", message: "expired", request_id: "55555555-5555-4555-8555-555555555555" } }), {
      status: 401,
      headers: { "content-type": "application/json", "x-request-id": "55555555-5555-4555-8555-555555555555", "set-cookie": "paper_trading_session=live; Path=/" }
    })));
    const response = await GET(new Request("http://localhost/api/auth/me"), { params: Promise.resolve({ path: ["me"] }) });
    expect(response.headers.get("x-request-id")).toBe("55555555-5555-4555-8555-555555555555");
    expect(response.headers.get("set-cookie")).toContain("paper_trading_session=live");
    expect(response.headers.get("set-cookie")).toContain("paper_trading_session=");
    expect(response.headers.get("set-cookie")).not.toContain("paper_trading_csrf=");
  });

  it("preserves a backend auth-unavailable response", async () => {
    process.env.PAPER_TRADING_API_BASE_URL = "http://backend.test";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { code: "AUTH_UNAVAILABLE", message: "backend down", request_id: "66666666-6666-4666-8666-666666666666" } }), {
      status: 503, headers: { "x-request-id": "66666666-6666-4666-8666-666666666666" }
    })));
    const response = await GET(new Request("http://localhost/api/auth/me"), { params: Promise.resolve({ path: ["me"] }) });
    expect(response.headers.get("x-request-id")).toBe("66666666-6666-4666-8666-666666666666");
    await expect(response.json()).resolves.toEqual({ detail: { code: "AUTH_UNAVAILABLE", message: "backend down", request_id: "66666666-6666-4666-8666-666666666666" } });
  });
});
