import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiGet, createAccount } from "./api-client";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("api client", () => {
  it("parses successful JSON responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify([{ id: 1 }]), { status: 200 })));
    await expect(apiGet<{ id: number }[]>("/accounts")).resolves.toEqual([{ id: 1 }]);
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
    expect(fetchMock).toHaveBeenCalledWith("/api/paper/accounts", expect.objectContaining({ method: "POST" }));
  });
});

describe("ApiError", () => {
  it("keeps status, code, and details", () => {
    const error = new ApiError(409, "ORDER_NOT_CANCELLABLE", "Cannot cancel", { id: 1 });
    expect(error.status).toBe(409);
    expect(error.details).toEqual({ id: 1 });
  });
});
