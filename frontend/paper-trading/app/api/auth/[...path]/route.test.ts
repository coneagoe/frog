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
});
