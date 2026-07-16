import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiGet, createAccount, importPositions } from "./api-client";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("api client", () => {
  it("parses successful JSON responses", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([{ id: 1 }]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(apiGet<{ id: number }[]>("/accounts")).resolves.toEqual([{ id: 1 }]);
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.has("content-type")).toBe(false);
  });

  it("normalizes structured backend errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ code: "INSUFFICIENT_CASH", message: "No cash" }), { status: 400 })
      )
    );
    await expect(apiGet("/accounts")).rejects.toMatchObject({
      status: 400,
      code: "INSUFFICIENT_CASH",
      message: "No cash"
    });
  });

  it("posts account creation payloads", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 1 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await createAccount({ name: "demo", initial_cash: "100000.00" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/paper/accounts",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ name: "demo", initial_cash: "100000.00" }) })
    );
  });

  it("posts import positions payloads", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ imported_count: 1, lots_count: 1 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await importPositions(7, {
      positions: [{ symbol: "000001", quantity: 100, cost_price: "10.23", buy_trade_date: "2026-01-15" }]
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/paper/accounts/7/positions/import",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          positions: [{ symbol: "000001", quantity: 100, cost_price: "10.23", buy_trade_date: "2026-01-15" }]
        })
      })
    );
  });
});

describe("ApiError", () => {
  it("keeps status, code, and details", () => {
    const error = new ApiError(409, "ORDER_NOT_CANCELLABLE", "Cannot cancel", { id: 1 });
    expect(error.status).toBe(409);
    expect(error.details).toEqual({ id: 1 });
  });

  it("uses text from non-object JSON error payloads", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify("backend failed"), { status: 500 })));
    await expect(apiGet("/accounts")).rejects.toMatchObject({
      status: 500,
      code: "HTTP_ERROR",
      message: "backend failed"
    });
  });
});
