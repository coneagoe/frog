import { NextResponse, type NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login", "/register", "/forgot-password", "/reset-password", "/verify-email"];
const PROTECTED_PREFIXES = ["/accounts", "/orders", "/trades", "/trade", "/analytics"];

function isPublicPath(pathname: string) {
  return PUBLIC_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

function isProtectedPath(pathname: string) {
  return PROTECTED_PREFIXES.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

function getSafeReturnPath(pathname: string, search: string) {
  const candidate = `${pathname}${search}`;
  return /^\/(?!\/)/.test(candidate) && !candidate.includes("\\") ? candidate : "/accounts";
}

function isAuthenticated(request: NextRequest) {
  return request.cookies.has(process.env.PAPER_TRADING_SESSION_COOKIE_NAME ?? "paper_trading_session");
}

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (isPublicPath(pathname)) {
    return NextResponse.next();
  }

  if (!isProtectedPath(pathname) || isAuthenticated(request)) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("return_to", getSafeReturnPath(pathname, search));
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/accounts/:path*", "/orders/:path*", "/trades/:path*", "/trade/:path*", "/analytics/:path*", "/login", "/register", "/forgot-password", "/reset-password", "/verify-email"]
};
