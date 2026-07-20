import { ApiError, parseApiError } from "./api-error";
import type {
  Account,
  AnalyticsResponse,
  CashFlowInput,
  CashFlowResult,
  CashLedgerEntry,
  CreateAccountInput,
  CreateMatchingRunInput,
  CreateOrderInput,
  ImportPositionsInput,
  ImportPositionsResult,
  MatchingRun,
  Order,
  Position,
  Snapshot,
  Trade,
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

export function listOrders(accountId: number): Promise<Order[]> {
  return apiGet<Order[]>(`/accounts/${accountId}/orders`);
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

export function listTrades(accountId: number): Promise<Trade[]> {
  return apiGet<Trade[]>(`/accounts/${accountId}/trades`);
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
