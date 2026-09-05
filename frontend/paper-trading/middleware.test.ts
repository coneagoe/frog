import { NextRequest } from "next/server";
import { afterEach, describe, expect, it } from "vitest";
import { middleware } from "./middleware";

function request(url: string, cookie?: string) {
  return new NextRequest(url, { headers: cookie ? { cookie } : undefined });
}

describe("middleware", () => {
  const originalSessionCookieName = process.env.PAPER_TRADING_SESSION_COOKIE_NAME;

  afterEach(() => {
    if (originalSessionCookieName === undefined) {
      delete process.env.PAPER_TRADING_SESSION_COOKIE_NAME;
    } else {
      process.env.PAPER_TRADING_SESSION_COOKIE_NAME = originalSessionCookieName;
    }
  });

  it("redirects anonymous visitors from protected pages to login with a safe return path", () => {
    const response = middleware(request("http://localhost:3000/orders?status=open"));
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("http://localhost:3000/login?return_to=%2Forders%3Fstatus%3Dopen");
  });

  it("preserves public auth routes", () => {
    const response = middleware(request("http://localhost:3000/login?return_to=/orders"));
    expect(response.headers.get("location")).toBeNull();
    expect(response.status).toBe(200);
  });

  it("allows authenticated requests through", () => {
    const response = middleware(request("http://localhost:3000/accounts", "paper_trading_session=session"));
    expect(response.headers.get("location")).toBeNull();
    expect(response.status).toBe(200);
  });

  it("uses the configured session cookie name", () => {
    process.env.PAPER_TRADING_SESSION_COOKIE_NAME = "custom_session";
    const response = middleware(request("http://localhost:3000/accounts", "custom_session=session"));
    expect(response.headers.get("location")).toBeNull();
    expect(response.status).toBe(200);
  });

  it("does not redirect routes outside the protected business areas", () => {
    const response = middleware(request("http://localhost:3000/"));
    expect(response.headers.get("location")).toBeNull();
    expect(response.status).toBe(200);
  });
});
