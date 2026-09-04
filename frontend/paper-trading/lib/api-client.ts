import { ApiError, parseApiError } from "./api-error";
import type {
  Account,
  AuthIdentity,
  AuthInput,
  ForgotPasswordInput,
  AnalyticsResponse,
  CashFlowInput,
  CashFlowResult,
  CashLedgerEntry,
  CorporateActionEvent,
  CorporateActionInput,
  CorporateActionResult,
  CreateAccountInput,
  CreateMatchingRunInput,
  CreateOrderInput,
  ImportPositionsInput,
  ImportPositionsResult,
  ListOrdersParams,
  ListCorporateActionsParams,
  ListTradesParams,
  MatchingRun,
  Order,
  OrderPage,
  Position,
  Snapshot,
  TradePage,
  ResetPasswordInput,
  ResendVerificationEmailInput,
  UpdateAccountFeesInput
} from "./types";

export { ApiError };

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  const response = await fetch(`/api/paper${path}`, {
    ...init,
    headers
  });
  if (!response.ok) {
    throw await parseApiError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

async function authRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  const response = await fetch(`/api${path}`, {
    ...init,
    credentials: "same-origin",
    headers
  });
  if (!response.ok) {
    throw await parseApiError(response);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function readCsrfToken(): string | undefined {
  const cookie = document.cookie.split("; ").find((item) => item.startsWith("paper_trading_csrf="));
  if (!cookie) return undefined;
  try {
    return decodeURIComponent(cookie.slice("paper_trading_csrf=".length));
  } catch {
    return undefined;
  }
}

export function register(input: AuthInput): Promise<AuthIdentity> {
  return authRequest<AuthIdentity>("/auth/register", { method: "POST", body: JSON.stringify(input) });
}

export function login(input: AuthInput): Promise<AuthIdentity> {
  return authRequest<AuthIdentity>("/auth/login", { method: "POST", body: JSON.stringify(input) });
}

export function forgotPassword(input: ForgotPasswordInput): Promise<void> {
  return authRequest<void>("/auth/forgot-password", { method: "POST", body: JSON.stringify(input) });
}

export function verifyEmail(token: string): Promise<{ message: string }> {
  const query = new URLSearchParams({ token });
  return authRequest<{ message: string }>(`/auth/verify-email?${query.toString()}`);
}

export function resendVerificationEmail(input: ResendVerificationEmailInput): Promise<{ message: string }> {
  return authRequest<{ message: string }>("/auth/resend-verification-email", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export function resetPassword(input: ResetPasswordInput): Promise<void> {
  return authRequest<void>("/auth/reset-password", { method: "POST", body: JSON.stringify(input) });
}

export function getCurrentUser(): Promise<AuthIdentity> {
  return authRequest<AuthIdentity>("/auth/me");
}

export function logout(): Promise<void> {
  const csrfToken = readCsrfToken();
  return authRequest<void>("/auth/logout", {
    method: "POST",
    headers: csrfToken ? { "X-CSRF-Token": csrfToken } : undefined
  });
}

export function apiGet<T>(path: string): Promise<T> {
  return apiRequest<T>(path);
}

export function createAccount(input: CreateAccountInput): Promise<Account> {
  return apiRequest<Account>("/accounts", { method: "POST", body: JSON.stringify(input) });
}

export function listAccounts(): Promise<Account[]> {
  return apiGet<Account[]>("/accounts");
}

export function getAnalytics(accountId: number): Promise<AnalyticsResponse> {
  return apiGet<AnalyticsResponse>(`/accounts/${accountId}/analytics`);
}

export function deleteAccount(accountId: number): Promise<void> {
  return apiRequest<void>(`/accounts/${accountId}`, { method: "DELETE" });
}

export function listPositions(accountId: number): Promise<Position[]> {
  return apiGet<Position[]>(`/accounts/${accountId}/positions`);
}

export function listOrders(accountId: number, params?: ListOrdersParams): Promise<OrderPage> {
  const query = new URLSearchParams();
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) {
        query.set(key, String(value));
      }
    }
  }
  const queryString = query.toString();
  return apiGet<OrderPage>(`/accounts/${accountId}/orders${queryString ? `?${queryString}` : ""}`);
}

export function createOrder(accountId: number, input: CreateOrderInput): Promise<Order> {
  return apiRequest<Order>(`/accounts/${accountId}/orders`, { method: "POST", body: JSON.stringify(input) });
}

export function cancelOrder(orderId: number): Promise<Order> {
  return apiRequest<Order>(`/orders/${orderId}/cancel`, { method: "POST" });
}

export function deleteOrder(orderId: number): Promise<void> {
  return apiRequest<void>(`/orders/${orderId}`, { method: "DELETE" });
}

export function updateOrderComment(orderId: number, comment: string): Promise<Order> {
  return apiRequest<Order>(`/orders/${orderId}/comment`, { method: "PATCH", body: JSON.stringify({ comment }) });
}

export function listTrades(accountId: number, params?: ListTradesParams): Promise<TradePage> {
  const query = new URLSearchParams();
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) {
        query.set(key, String(value));
      }
    }
  }
  const queryString = query.toString();
  return apiGet<TradePage>(`/accounts/${accountId}/trades${queryString ? `?${queryString}` : ""}`);
}

export function listCashLedger(accountId: number): Promise<CashLedgerEntry[]> {
  return apiGet<CashLedgerEntry[]>(`/accounts/${accountId}/cash-ledger`);
}

export function listSnapshots(accountId: number): Promise<Snapshot[]> {
  return apiGet<Snapshot[]>(`/accounts/${accountId}/snapshots`);
}

export function createMatchingRun(input: CreateMatchingRunInput): Promise<MatchingRun> {
  return apiRequest<MatchingRun>("/matching/runs", { method: "POST", body: JSON.stringify(input) });
}

export function updateAccountFees(accountId: number, input: UpdateAccountFeesInput): Promise<Account> {
  return apiRequest<Account>(`/accounts/${accountId}`, { method: "PATCH", body: JSON.stringify(input) });
}

export function importPositions(accountId: number, input: ImportPositionsInput): Promise<ImportPositionsResult> {
  return apiRequest<ImportPositionsResult>(`/accounts/${accountId}/positions/import`, {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export function depositCash(accountId: number, input: CashFlowInput): Promise<CashFlowResult> {
  return apiRequest<CashFlowResult>(`/accounts/${accountId}/cash/deposit`, { method: "POST", body: JSON.stringify(input) });
}

export function withdrawCash(accountId: number, input: CashFlowInput): Promise<CashFlowResult> {
  return apiRequest<CashFlowResult>(`/accounts/${accountId}/cash/withdraw`, { method: "POST", body: JSON.stringify(input) });
}

export function createCorporateAction(accountId: number, input: CorporateActionInput): Promise<CorporateActionResult> {
  return apiRequest<CorporateActionResult>(`/accounts/${accountId}/corporate-actions`, {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export function listCorporateActions(accountId: number, params?: ListCorporateActionsParams): Promise<CorporateActionEvent[]> {
  const query = new URLSearchParams();
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) query.set(key, value);
    }
  }
  const queryString = query.toString();
  return apiGet<CorporateActionEvent[]>(
    `/accounts/${accountId}/corporate-actions${queryString ? `?${queryString}` : ""}`
  );
}
