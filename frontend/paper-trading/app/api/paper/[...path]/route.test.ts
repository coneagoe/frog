import { afterEach, describe, expect, it, vi } from "vitest";
import { DELETE, GET, POST } from "./route";

afterEach(() => {
  vi.restoreAllMocks();
  delete process.env.PAPER_TRADING_API_BASE_URL;
  delete process.env.PAPER_TRADING_API_TOKEN;
});

describe("paper API proxy", () => {
  it("forwards GET requests with bearer token", async () => {
    process.env.PAPER_TRADING_API_BASE_URL = "http://backend.test";
    process.env.PAPER_TRADING_API_TOKEN = "secret";
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([{ id: 1 }]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(new Request("http://localhost/api/paper/accounts?x=1"), {
      params: Promise.resolve({ path: ["accounts"] })
    });

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://backend.test/paper/accounts?x=1",
      expect.objectContaining({ headers: expect.any(Headers) })
    );
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get("authorization")).toBe("Bearer secret");
    expect(headers.has("content-type")).toBe(false);
  });

  it("forwards POST JSON bodies", async () => {
    process.env.PAPER_TRADING_API_BASE_URL = "http://backend.test";
    process.env.PAPER_TRADING_API_TOKEN = "secret";
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 1 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const body = JSON.stringify({ name: "demo", initial_cash: "100000.00" });

    await POST(
      new Request("http://localhost/api/paper/accounts", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body
      }),
      { params: Promise.resolve({ path: ["accounts"] }) }
    );

    expect(fetchMock.mock.calls[0][1].body).toBeInstanceOf(ReadableStream);
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get("content-type")).toBe("application/json");
  });

  it("forwards DELETE requests without a body", async () => {
    process.env.PAPER_TRADING_API_BASE_URL = "http://backend.test";
    process.env.PAPER_TRADING_API_TOKEN = "secret";
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
    expect(headers.get("authorization")).toBe("Bearer secret");
    expect(headers.has("content-type")).toBe(false);
  });
});
