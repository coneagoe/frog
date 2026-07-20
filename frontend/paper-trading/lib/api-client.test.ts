import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiGet, createAccount, depositCash, importPositions, updateOrderComment, withdrawCash } from "./api-client";

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

  it("sends updateOrderComment PATCH", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 1, comment: "updated" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await updateOrderComment(42, "updated comment");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/paper/orders/42/comment",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ comment: "updated comment" })
      })
    );
  });

  it("sends empty string to clear comment", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 1, comment: null }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await updateOrderComment(42, "");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/paper/orders/42/comment",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ comment: "" })
      })
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

describe("cash flow API", () => {
  it("posts deposit cash payloads", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ account_id: 7 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await depositCash(7, { amount: "10000", trade_date: "2026-07-20", note: "add cash" });
    expect(fetchMock).toHaveBeenCalledWith("/api/paper/accounts/7/cash/deposit", expect.objectContaining({ method: "POST", body: JSON.stringify({ amount: "10000", trade_date: "2026-07-20", note: "add cash" }) }));
  });

  it("posts withdraw cash payloads", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ account_id: 7 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await withdrawCash(7, { amount: "5000", trade_date: "2026-07-20" });
    expect(fetchMock).toHaveBeenCalledWith("/api/paper/accounts/7/cash/withdraw", expect.objectContaining({ method: "POST", body: JSON.stringify({ amount: "5000", trade_date: "2026-07-20" }) }));
  });
});
