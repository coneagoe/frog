import { createServer } from "node:http";
import { randomUUID } from "node:crypto";

const port = Number(process.env.PAPER_TRADING_E2E_AUTH_PORT ?? "8100");
const users = new Map();
const verificationTokens = new Map();
const sessions = new Set();

function sendJson(response, status, body, headers = {}) {
  response.writeHead(status, { "content-type": "application/json", ...headers });
  response.end(JSON.stringify(body));
}

function readBody(request) {
  return new Promise((resolve, reject) => {
    let body = "";
    request.setEncoding("utf8");
    request.on("data", (chunk) => { body += chunk; });
    request.on("end", () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (error) {
        reject(error);
      }
    });
  });
}

function hasSession(request) {
  const cookies = request.headers.cookie ?? "";
  return [...sessions].some((session) => cookies.includes(`paper_trading_session=${session}`));
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", `http://127.0.0.1:${port}`);

  if (request.method === "GET" && url.pathname === "/") {
    sendJson(response, 200, { status: "ready" });
    return;
  }

  if (request.method === "POST" && url.pathname === "/auth/register") {
    const { email, password } = await readBody(request);
    const normalizedEmail = String(email).trim().toLowerCase();
    if (!normalizedEmail || !password || users.has(normalizedEmail)) {
      sendJson(response, 400, { code: "BAD_REQUEST" });
      return;
    }
    const verificationToken = randomUUID();
    users.set(normalizedEmail, { password, verified: false, verificationToken });
    verificationTokens.set(verificationToken, normalizedEmail);
    sendJson(response, 201, { id: users.size, email: normalizedEmail, email_verified_at: null });
    return;
  }

  if (request.method === "GET" && url.pathname === "/__test__/mail/latest") {
    const email = url.searchParams.get("email")?.trim().toLowerCase();
    const user = email ? users.get(email) : undefined;
    if (!user) {
      sendJson(response, 404, { code: "NOT_FOUND" });
      return;
    }
    // The capture seam stays test-only; its response is never logged by the test runner.
    sendJson(response, 200, { verificationPath: `/verify-email?token=${encodeURIComponent(user.verificationToken)}` });
    return;
  }

  if (request.method === "GET" && url.pathname === "/auth/verify-email") {
    const email = verificationTokens.get(url.searchParams.get("token"));
    const user = email ? users.get(email) : undefined;
    if (!user) {
      sendJson(response, 400, { code: "INVALID_TOKEN" });
      return;
    }
    user.verified = true;
    verificationTokens.delete(user.verificationToken);
    sendJson(response, 200, { message: "verified" });
    return;
  }

  if (request.method === "POST" && url.pathname === "/auth/login") {
    const { email, password } = await readBody(request);
    const user = users.get(String(email).trim().toLowerCase());
    if (!user || !user.verified || user.password !== password) {
      sendJson(response, 401, { code: "UNAUTHORIZED" });
      return;
    }
    const session = randomUUID();
    const csrf = randomUUID();
    sessions.add(session);
    sendJson(response, 200, { id: 1, email: String(email).trim().toLowerCase(), email_verified_at: "2026-01-01T00:00:00Z" }, {
      "set-cookie": [
        `paper_trading_session=${session}; Path=/; HttpOnly; SameSite=Lax`,
        `paper_trading_csrf=${csrf}; Path=/; SameSite=Lax`
      ]
    });
    return;
  }

  if (request.method === "GET" && url.pathname === "/paper/accounts") {
    if (!hasSession(request)) {
      sendJson(response, 401, { code: "UNAUTHORIZED" });
      return;
    }
    sendJson(response, 200, [{
      id: 1,
      name: "Authenticated E2E Account",
      initial_cash: "100000.0000",
      cash_available: "100000.0000",
      status: "active",
      base_currency: "CNY",
      fee_preset: "a_share_default",
      commission_rate: "0.000300",
      min_commission: "5.0000",
      stamp_duty_rate: "0.000500",
      transfer_fee_rate: "0.000010",
      share_count: "1.0000",
      net_asset_value: "100000.0000",
      cumulative_deposit: "100000.0000",
      cumulative_withdrawal: "0.0000"
    }]);
    return;
  }

  sendJson(response, 404, { code: "NOT_FOUND" });
});

server.listen(port, "127.0.0.1");
