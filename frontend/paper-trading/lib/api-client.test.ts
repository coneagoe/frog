import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  apiGet,
  createCorporateAction,
  createAccount,
  deleteAccount,
  deleteMonitorTarget,
  depositCash,
  createMonitorTarget,
  getMonitorTarget,
  getMonitorTargetHealth,
  importPositions,
  listMonitorTargets,
  listOrders,
  listCorporateActions,
  listTrades,
  setMonitorTargetEnabled,
  updateMonitorTarget,
  updateOrderComment,
  withdrawCash
} from "./api-client";
import { forgotPassword, getCurrentUser, login, logout, register, resendVerificationEmail, resetPassword, verifyEmail } from "./api-client";
import type { MonitorTarget, MonitorTargetHealth } from "./types";

afterEach(() => {
  vi.restoreAllMocks();
  document.cookie = "paper_trading_csrf=; Max-Age=0; path=/";
});

describe("api client", () => {
  it("uses same-origin auth URLs and credentials", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 1, email: "user@example.com", email_verified_at: null }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await login({ email: "user@example.com", password: "Validpassword1" });
    expect(fetchMock).toHaveBeenCalledWith("/api/auth/login", expect.objectContaining({ credentials: "same-origin" }));
  });

  it("exposes auth methods and parses structured errors", async () => {
    const identity = { id: 1, email: "user@example.com", email_verified_at: null };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(identity), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(identity), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(identity), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: "UNAUTHORIZED", message: "Unauthorized" }), { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(register({ email: identity.email, password: "Validpassword1" })).resolves.toEqual(identity);
    await expect(login({ email: identity.email, password: "Validpassword1" })).resolves.toEqual(identity);
    await expect(getCurrentUser()).resolves.toEqual(identity);
    await expect(logout()).rejects.toMatchObject({ status: 401, code: "UNAUTHORIZED" });
  });

  it("posts forgot-password and reset-password requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    await forgotPassword({ email: "user@example.com" });
    await resetPassword({ token: "reset-token", password: "Validpassword1" });
    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/auth/forgot-password", expect.objectContaining({ method: "POST", body: JSON.stringify({ email: "user@example.com" }) }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/auth/reset-password", expect.objectContaining({ method: "POST", body: JSON.stringify({ token: "reset-token", password: "Validpassword1" }) }));
  });

  it("posts verification requests", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ message: "ok" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ message: "ok" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await verifyEmail("verify token");
    await resendVerificationEmail({ email: "user@example.com" });
    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/auth/verify-email?token=verify+token", expect.objectContaining({ credentials: "same-origin" }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/auth/resend-verification-email", expect.objectContaining({ method: "POST", body: JSON.stringify({ email: "user@example.com" }) }));
  });

  it("sends logout CSRF header for a valid cookie and omits it for malformed cookies", async () => {
    document.cookie = "paper_trading_csrf=csrf%2Dvalue";
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    await logout();
    expect((fetchMock.mock.calls[0][1].headers as Headers).get("X-CSRF-Token")).toBe("csrf-value");

    document.cookie = "paper_trading_csrf=%%%";
    await logout();
    expect((fetchMock.mock.calls[1][1].headers as Headers).has("X-CSRF-Token")).toBe(false);
  });
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
    document.cookie = "paper_trading_csrf=csrf%2Dvalue";
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 1 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await createAccount({ name: "demo", initial_cash: "100000.00" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/paper/accounts",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ name: "demo", initial_cash: "100000.00" }) })
    );
    expect((fetchMock.mock.calls[0][1].headers as Headers).get("X-CSRF-Token")).toBe("csrf-value");
  });

  it("adds the CSRF header to PATCH and DELETE business requests", async () => {
    document.cookie = "paper_trading_csrf=csrf%2Dvalue";
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 1, comment: "updated" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await updateOrderComment(42, "updated");
    await deleteAccount(1);

    expect((fetchMock.mock.calls[0][1].headers as Headers).get("X-CSRF-Token")).toBe("csrf-value");
    expect((fetchMock.mock.calls[1][1].headers as Headers).get("X-CSRF-Token")).toBe("csrf-value");
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
      positions: [{ symbol: "000001", quantity: 100, cost_price: "10.23", buy_trade_date: "2026-01-15", market: "a_share" }]
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/paper/accounts/7/positions/import",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          positions: [{ symbol: "000001", quantity: 100, cost_price: "10.23", buy_trade_date: "2026-01-15", market: "a_share" }]
        })
      })
    );
  });
});

describe("listOrders", () => {
  const orderPage = {
    items: [{ id: 42, account_id: 7, symbol: "AAPL", status: "accepted" }],
    page: 2,
    page_size: 25,
    total_count: 30,
    total_pages: 2
  };

  it("resolves with the OrderPage envelope", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(orderPage), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(listOrders(7)).resolves.toEqual(orderPage);
  });

  it("serializes every defined query param", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(orderPage), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await listOrders(7, { start_date: "2026-06-01", end_date: "2026-06-30", page: 2, page_size: 25 });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/paper/accounts/7/orders?start_date=2026-06-01&end_date=2026-06-30&page=2&page_size=25",
      expect.anything()
    );
  });

  it("omits undefined query params", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(orderPage), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await listOrders(7, { start_date: undefined, end_date: "2026-06-30", page: undefined, page_size: 25 });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/paper/accounts/7/orders?end_date=2026-06-30&page_size=25",
      expect.anything()
    );
  });

  it("omits the query string when no params are given", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(orderPage), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await listOrders(7);
    expect(fetchMock).toHaveBeenCalledWith("/api/paper/accounts/7/orders", expect.anything());
  });
});

describe("listTrades", () => {
  const tradePage = {
    items: [{ id: 42, account_id: 7, symbol: "AAPL", quantity: 10 }],
    page: 2,
    page_size: 25,
    total_count: 30,
    total_pages: 2
  };

  it("resolves with the TradePage envelope and serializes every defined query param", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(tradePage), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      listTrades(7, { start_date: "2026-08-01", end_date: "2026-08-02", page: 2, page_size: 25 })
    ).resolves.toEqual(tradePage);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/paper/accounts/7/trades?start_date=2026-08-01&end_date=2026-08-02&page=2&page_size=25",
      expect.anything()
    );
  });

  it("omits undefined query params", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(tradePage), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await listTrades(7, { start_date: undefined, end_date: "2026-08-02", page: undefined, page_size: 25 });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/paper/accounts/7/trades?end_date=2026-08-02&page_size=25",
      expect.anything()
    );
  });

  it("omits the query string when no params are given", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(tradePage), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await listTrades(7);
    expect(fetchMock).toHaveBeenCalledWith("/api/paper/accounts/7/trades", expect.anything());
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

  it.each([
    [{ detail: "at least one update is required" }, "at least one update is required"],
    [{ detail: { field: "condition", reason: "invalid" } }, "field: condition, reason: invalid"],
    [{ detail: [{ loc: ["body", "market"], msg: "Field required", type: "missing" }] }, "body.market: Field required"]
  ])("uses FastAPI detail payloads as usable errors", async (payload, message) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status: 422 })));

    await expect(apiGet("/accounts")).rejects.toMatchObject({ status: 422, code: "HTTP_ERROR", message });
  });
});

describe("monitor target API", () => {
  const target: MonitorTarget = {
    id: 7,
    stock_code: "00700",
    market: "HK",
    condition: { type: "price_threshold", direction: "below", value: 300 },
    note: "watch Tencent",
    frequency: "daily",
    reset_mode: "auto",
    enabled: true,
    last_state: false,
    triggered_at: null,
    created_at: "2026-09-06T09:30:00Z"
  };

  it("retains false list filters and encodes defined filters", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([target]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(listMonitorTargets({ enabled: false, market: "HK" })).resolves.toEqual([target]);

    expect(fetchMock).toHaveBeenCalledWith("/api/paper/monitor-targets?market=HK&enabled=false", expect.anything());
  });

  it("gets the operational health for manual and workflow targets", async () => {
    document.cookie = "paper_trading_csrf=csrf%2Dvalue";
    const health: MonitorTargetHealth = {
      summary: { total: 2, running: 1, paused: 1, disabled: 0, triggered: 1, daily: 1, intraday: 1 },
      targets: [
        { id: 7, stock_code: "00700", market: "HK", frequency: "daily", workflow: null, enabled: true, paused: false, operational_state: "running", last_state: true, last_checked_at: "2026-09-07T09:30:00Z", triggered_at: "2026-09-07T09:30:00Z", latest_error: null },
        { id: 8, stock_code: "000001", market: "A", frequency: "intraday", workflow: "morning-watch", enabled: true, paused: true, operational_state: "paused", last_state: false, last_checked_at: null, triggered_at: null, latest_error: { kind: "market_data", summary: "Quote unavailable", detail: "Provider timeout", occurred_at: "2026-09-07T09:31:00Z" } }
      ]
    };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(health), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getMonitorTargetHealth()).resolves.toEqual(health);

    expect(fetchMock).toHaveBeenCalledWith("/api/paper/monitor-targets/health", expect.anything());
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.method ?? "GET").toBe("GET");
    expect((init.headers as Headers).get("X-CSRF-Token")).toBeNull();
  });

  it("sends monitor target CRUD requests with CSRF protection", async () => {
    document.cookie = "paper_trading_csrf=csrf%2Dvalue";
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(target), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(target), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...target, note: null }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...target, enabled: false }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const input = { stock_code: "00700", market: "HK" as const, condition: target.condition, note: target.note };

    await createMonitorTarget(input);
    await getMonitorTarget(target.id);
    await updateMonitorTarget(target.id, { note: null });
    await setMonitorTargetEnabled(target.id, false);
    await deleteMonitorTarget(target.id);

    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/paper/monitor-targets", expect.objectContaining({ method: "POST", body: JSON.stringify(input) }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/paper/monitor-targets/7", expect.anything());
    expect(fetchMock).toHaveBeenNthCalledWith(3, "/api/paper/monitor-targets/7", expect.objectContaining({ method: "PATCH", body: JSON.stringify({ note: null }) }));
    expect(fetchMock).toHaveBeenNthCalledWith(4, "/api/paper/monitor-targets/7/enabled", expect.objectContaining({ method: "PATCH", body: JSON.stringify({ enabled: false }) }));
    expect(fetchMock).toHaveBeenNthCalledWith(5, "/api/paper/monitor-targets/7", expect.objectContaining({ method: "DELETE" }));
    for (const [, init] of [fetchMock.mock.calls[0], fetchMock.mock.calls[2], fetchMock.mock.calls[3], fetchMock.mock.calls[4]]) {
      expect((init.headers as Headers).get("X-CSRF-Token")).toBe("csrf-value");
    }
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

describe("corporate action API", () => {
  it("posts corporate action payloads", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ event: {}, impact: {}, recalculation: {} }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const input = {
      symbol: "510300.SH",
      market: "etf" as const,
      event_type: "rights_issue" as const,
      event_at: "2026-08-27T09:30:00+08:00",
      idempotency_key: "rights-1",
      parameters: { subscription_ratio: "0.1000", subscription_price: "3.25" }
    };

    await createCorporateAction(7, input);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/paper/accounts/7/corporate-actions",
      expect.objectContaining({ method: "POST", body: JSON.stringify(input) })
    );
  });

  it("encodes defined corporate action filters and omits undefined values", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("[]", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await listCorporateActions(7, { symbol: "A B&", event_type: "reverse_split", start_at: "2026-01-01T00:00:00Z", end_at: undefined });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/paper/accounts/7/corporate-actions?symbol=A+B%26&event_type=reverse_split&start_at=2026-01-01T00%3A00%3A00Z",
      expect.anything()
    );
  });
});
