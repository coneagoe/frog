import { ApiError, parseApiError } from "./api-error";
import type {
  Account,
  CashLedgerEntry,
  CreateAccountInput,
  CreateMatchingRunInput,
  CreateOrderInput,
  MatchingRun,
  Order,
  Position,
  Snapshot,
  Trade
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
