import { afterEach, describe, expect, it, vi } from "vitest";
import { DELETE, GET, PATCH, POST } from "./route";

afterEach(() => {
  vi.restoreAllMocks();
  delete process.env.PAPER_TRADING_API_BASE_URL;
});

describe("paper API proxy", () => {
  it("forwards GET cookies without a bearer token", async () => {
    process.env.PAPER_TRADING_API_BASE_URL = "http://backend.test";
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([{ id: 1 }]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(new Request("http://localhost/api/paper/accounts?x=1", { headers: { cookie: "paper_trading_session=session" } }), {
      params: Promise.resolve({ path: ["accounts"] })
    });

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://backend.test/paper/accounts?x=1",
      expect.objectContaining({ headers: expect.any(Headers) })
    );
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get("cookie")).toBe("paper_trading_session=session");
    expect(headers.has("authorization")).toBe(false);
    expect(headers.has("content-type")).toBe(false);
  });

  it("forwards POST body, cookies, content type, and CSRF header", async () => {
    process.env.PAPER_TRADING_API_BASE_URL = "http://backend.test";
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 1 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const body = JSON.stringify({ name: "demo", initial_cash: "100000.00" });

    await POST(
      new Request("http://localhost/api/paper/accounts", {
        method: "POST",
        headers: { cookie: "paper_trading_session=session", "content-type": "application/json", "x-csrf-token": "csrf-token" },
        body
      }),
      { params: Promise.resolve({ path: ["accounts"] }) }
    );

    expect(fetchMock.mock.calls[0][1].body).toBeInstanceOf(ReadableStream);
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get("cookie")).toBe("paper_trading_session=session");
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("x-csrf-token")).toBe("csrf-token");
  });

  it("forwards PATCH JSON bodies", async () => {
    process.env.PAPER_TRADING_API_BASE_URL = "http://backend.test";
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 1 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const body = JSON.stringify({ commission_rate: "0.0001" });

    await PATCH(
      new Request("http://localhost/api/paper/accounts/1", {
        method: "PATCH",
        headers: { "content-type": "application/json", "x-csrf-token": "csrf-token" },
        body
      }),
      { params: Promise.resolve({ path: ["accounts", "1"] }) }
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "http://backend.test/paper/accounts/1",
      expect.objectContaining({ method: "PATCH", headers: expect.any(Headers) })
    );
    expect(fetchMock.mock.calls[0][1].body).toBeInstanceOf(ReadableStream);
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("x-csrf-token")).toBe("csrf-token");
  });

  it("forwards DELETE requests without a body", async () => {
    process.env.PAPER_TRADING_API_BASE_URL = "http://backend.test";
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await DELETE(new Request("http://localhost/api/paper/accounts/1", { method: "DELETE" }), {
      params: Promise.resolve({ path: ["accounts", "1"] })
    });

    expect(response.status).toBe(204);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://backend.test/paper/accounts/1",
      expect.objectContaining({ method: "DELETE", body: null })
    );
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.has("authorization")).toBe(false);
    expect(headers.has("content-type")).toBe(false);
  });

  it("preserves upstream error and set-cookie headers", async () => {
    process.env.PAPER_TRADING_API_BASE_URL = "http://backend.test";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ code: "UNAUTHORIZED" }), {
          status: 401,
          headers: { "content-type": "application/json", "set-cookie": "paper_trading_csrf=next; Path=/" }
        })
      )
    );

    const response = await GET(new Request("http://localhost/api/paper/accounts"), {
      params: Promise.resolve({ path: ["accounts"] })
    });

    expect(response.status).toBe(401);
    expect(response.headers.get("set-cookie")).toBe("paper_trading_csrf=next; Path=/");
    await expect(response.json()).resolves.toEqual({ code: "UNAUTHORIZED" });
  });
});
