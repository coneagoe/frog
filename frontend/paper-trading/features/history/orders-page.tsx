"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorBanner } from "@/components/error-banner";
import { cancelOrder, deleteOrder, listAccounts, listOrders, updateOrderComment } from "@/lib/api-client";
import type { Account, Order } from "@/lib/types";
import { OrderTable } from "@/features/trading/trading-tables";

const PAGE_SIZE = 25;
const SHANGHAI_TIME_ZONE = "Asia/Shanghai";
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

export type RangePreset = "today" | "7d" | "30d";

type OrdersQuery = {
  accountId: number | null;
  startDate: string;
  endDate: string;
  page: number;
};

type SearchParamsLike = {
  get(name: string): string | null;
};

// "Today" on the Asia/Shanghai calendar. Reading the parts through Intl avoids
// the UTC truncation bug of new Date().toISOString().slice(0, 10).
export function shanghaiToday(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: SHANGHAI_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).formatToParts(new Date());
  const part = (type: string) => parts.find((entry) => entry.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

// Pure calendar math on a YYYY-MM-DD string; UTC accessors keep this timezone-free.
export function shiftDate(date: string, days: number): string {
  const [year, month, day] = date.split("-").map(Number);
  const shifted = new Date(Date.UTC(year, month - 1, day + days));
  const yyyy = shifted.getUTCFullYear();
  const mm = String(shifted.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(shifted.getUTCDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export function presetRange(preset: RangePreset): [string, string] {
  const today = shanghaiToday();
  if (preset === "today") return [today, today];
  if (preset === "7d") return [shiftDate(today, -6), today];
  return [shiftDate(today, -29), today];
}

function isValidDateString(value: string): boolean {
  if (!DATE_PATTERN.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day;
}

function isValidRange(startDate: string, endDate: string): boolean {
  return isValidDateString(startDate) && isValidDateString(endDate) && startDate <= endDate;
}

function parseAccountId(value: string | null): number | null {
  if (value === null) return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function parsePage(value: string | null): number {
  if (value === null) return 1;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 1 ? parsed : 1;
}

// URL state is parsed once into primitives; missing or invalid dates fall back
// to the default trailing 30-day range so every request sends an explicit range.
function parseOrdersQuery(searchParams: SearchParamsLike): OrdersQuery {
  const start = searchParams.get("start_date");
  const end = searchParams.get("end_date");
  const urlRange = start !== null && end !== null && isValidRange(start, end) ? { start, end } : null;
  const [defaultStart, defaultEnd] = presetRange("30d");
  return {
    accountId: parseAccountId(searchParams.get("accountId")),
    startDate: urlRange?.start ?? defaultStart,
    endDate: urlRange?.end ?? defaultEnd,
    page: parsePage(searchParams.get("page"))
  };
}

function activePresetFor(startDate: string, endDate: string): RangePreset | null {
  const today = shanghaiToday();
  if (startDate === today && endDate === today) return "today";
  if (startDate === shiftDate(today, -6) && endDate === today) return "7d";
  if (startDate === shiftDate(today, -29) && endDate === today) return "30d";
  return null;
}

const PRESETS: { key: RangePreset; label: string }[] = [
  { key: "today", label: "Today" },
  { key: "7d", label: "Last 7 days" },
  { key: "30d", label: "Last 30 days" }
];

export function OrdersPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const initialQueryRef = useRef<OrdersQuery | null>(null);
  if (initialQueryRef.current === null) {
    initialQueryRef.current = parseOrdersQuery(searchParams);
  }
  const initialQuery = initialQueryRef.current;

  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [startDate, setStartDate] = useState(initialQuery.startDate);
  const [endDate, setEndDate] = useState(initialQuery.endDate);
  const [page, setPage] = useState(initialQuery.page);
  const [orders, setOrders] = useState<Order[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [ordersLoading, setOrdersLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingOrderId, setEditingOrderId] = useState<number | null>(null);
  const [editingValue, setEditingValue] = useState("");
  const [deletingOrderId, setDeletingOrderId] = useState<number | null>(null);
  const requestIdRef = useRef(0);

  const rangeValid = isValidRange(startDate, endDate);
  const activePreset = activePresetFor(startDate, endDate);

  const loadOrders = useCallback(async (accountId: number, rangeStart: string, rangeEnd: string, targetPage: number) => {
    const requestId = ++requestIdRef.current;
    setOrders([]);
    setOrdersLoading(true);
    setError(null);
    try {
      const result = await listOrders(accountId, {
        start_date: rangeStart,
        end_date: rangeEnd,
        page: targetPage,
        page_size: PAGE_SIZE
      });
      if (requestId === requestIdRef.current) {
        setOrders(result.items);
        setTotalCount(result.total_count);
        setTotalPages(result.total_pages);
        // The API clamps out-of-range pages to the last valid page; adopt it so a
        // mutation that empties the current page opens the preceding valid page.
        if (result.page !== targetPage) {
          setPage(result.page);
        }
      }
    } catch (err) {
      if (requestId === requestIdRef.current) {
        setError(err instanceof Error ? err.message : "Failed to load orders");
      }
    } finally {
      if (requestId === requestIdRef.current) {
        setOrdersLoading(false);
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const nextAccounts = await listAccounts();
        if (cancelled) return;
        setAccounts(nextAccounts);
        const requestedAccountId = initialQueryRef.current?.accountId ?? null;
        const firstAccountId = nextAccounts.some((account) => account.id === requestedAccountId)
          ? requestedAccountId
          : nextAccounts[0]?.id ?? null;
        setSelectedAccountId(firstAccountId);
        if (firstAccountId === null) {
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load orders data");
          setLoading(false);
        }
      }
    }
    void load();
    return () => { cancelled = true; };
  }, []);

  // Fetch whenever the account, range, or page changes. Every change also
  // invalidates any in-flight list request: loadOrders bumps the request id for
  // a valid view, and the invalid-range branch below bumps it directly, so a
  // late response can never overwrite the newer view. An invalid custom range
  // sends no request and keeps the last valid results on screen.
  useEffect(() => {
    if (selectedAccountId === null) return;
    if (!rangeValid) {
      requestIdRef.current += 1;
      setLoading(false);
      setOrdersLoading(false);
      return;
    }
    void loadOrders(selectedAccountId, startDate, endDate, page);
  }, [selectedAccountId, startDate, endDate, page, rangeValid, loadOrders]);

  // The URL mirrors the current view so it can be shared or refreshed; it keeps
  // the last valid range while the custom inputs hold an invalid one.
  useEffect(() => {
    if (selectedAccountId === null || !rangeValid) return;
    const params = new URLSearchParams({
      accountId: String(selectedAccountId),
      start_date: startDate,
      end_date: endDate,
      page: String(page)
    });
    router.replace(`/orders?${params.toString()}`);
  }, [selectedAccountId, startDate, endDate, page, rangeValid, router]);

  function handleAccountChange(accountId: number) {
    setSelectedAccountId(accountId);
    setPage(1);
  }

  function handlePresetClick(preset: RangePreset) {
    const [rangeStart, rangeEnd] = presetRange(preset);
    setStartDate(rangeStart);
    setEndDate(rangeEnd);
    setPage(1);
  }

  function handleStartDateChange(value: string) {
    setStartDate(value);
    setPage(1);
  }

  function handleEndDateChange(value: string) {
    setEndDate(value);
    setPage(1);
  }

  function handleEditStart(orderId: number) {
    const order = orders.find((o) => o.id === orderId);
    setEditingOrderId(orderId);
    setEditingValue(order?.comment ?? "");
  }

  function handleEditCancel() {
    setEditingOrderId(null);
    setEditingValue("");
  }

  async function handleEditSave(orderId: number) {
    const requestId = ++requestIdRef.current;
    setError(null);
    try {
      const updatedOrder = await updateOrderComment(orderId, editingValue);
      if (requestId === requestIdRef.current) {
        setOrders((prev) => prev.map((o) => (o.id === orderId ? updatedOrder : o)));
        setEditingOrderId(null);
        setEditingValue("");
      }
    } catch (err) {
      if (requestId === requestIdRef.current) {
        setError(err instanceof Error ? err.message : "Failed to update comment");
      }
    }
  }

  async function handleCancel(orderId: number) {
    const requestId = ++requestIdRef.current;
    setError(null);
    try {
      await cancelOrder(orderId);
      if (requestId === requestIdRef.current && selectedAccountId !== null && rangeValid) {
        await loadOrders(selectedAccountId, startDate, endDate, page);
      }
    } catch (err) {
      if (requestId === requestIdRef.current) {
        setError(err instanceof Error ? err.message : "Failed to cancel order");
      }
    }
  }

  async function handleDelete(orderId: number) {
    const confirmed = window.confirm(
      "Delete this order? Filled trades, cash ledger, positions, and snapshots for this paper account will be recalculated."
    );
    if (!confirmed) return;

    const requestId = ++requestIdRef.current;
    setDeletingOrderId(orderId);
    setError(null);
    try {
      await deleteOrder(orderId);
      if (requestId === requestIdRef.current && selectedAccountId !== null && rangeValid) {
        await loadOrders(selectedAccountId, startDate, endDate, page);
      }
    } catch (err) {
      if (requestId === requestIdRef.current) {
        setError(err instanceof Error ? err.message : "Failed to delete order");
      }
    } finally {
      setDeletingOrderId((current) => (current === orderId ? null : current));
    }
  }

  // loadOrders clears orders before fetching, so a single flag covers both the
  // initial load and later refetches.
  const showOrdersLoading = loading || ordersLoading;

  return (
    <section className="page">
      <div className="page__header">
        <div>
          <h1>Orders</h1>
          <p className="muted">Review and cancel historical paper orders.</p>
        </div>
        <label>
          <span className="account-selector">
            Account
            <select
              disabled={accounts.length === 0}
              value={selectedAccountId ?? ""}
              onChange={(event) => handleAccountChange(Number(event.target.value))}
            >
              {accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
            </select>
          </span>
        </label>
      </div>
      <div className="filter-bar">
        <div className="filter-bar__presets">
          {PRESETS.map((preset) => (
            <button
              aria-pressed={activePreset === preset.key}
              className={activePreset === preset.key ? "button" : "button button--secondary"}
              key={preset.key}
              onClick={() => handlePresetClick(preset.key)}
              type="button"
            >
              {preset.label}
            </button>
          ))}
        </div>
        <label className="filter-bar__field">
          <span>Start date</span>
          <input type="date" value={startDate} onChange={(event) => handleStartDateChange(event.target.value)} />
        </label>
        <label className="filter-bar__field">
          <span>End date</span>
          <input type="date" value={endDate} onChange={(event) => handleEndDateChange(event.target.value)} />
        </label>
      </div>
      {!rangeValid ? (
        <p className="filter-error" role="alert">
          {startDate === "" || endDate === ""
            ? "Choose both a start date and an end date to apply a custom range."
            : "Start date must be on or before end date."}
        </p>
      ) : null}
      {showOrdersLoading ? <div className="panel">Loading orders...</div> : null}
      {!loading && accounts.length === 0 ? <div className="panel">No paper accounts yet. Create an account before viewing orders.</div> : null}
      {error ? <ErrorBanner message={error} /> : null}
      {!showOrdersLoading && accounts.length > 0 ? (
        <>
          <OrderTable
            orders={orders}
            onCancel={handleCancel}
            onDelete={handleDelete}
            deletingOrderId={deletingOrderId}
            editingOrderId={editingOrderId}
            editingValue={editingValue}
            onEditStart={handleEditStart}
            onEditValueChange={setEditingValue}
            onEditSave={handleEditSave}
            onEditCancel={handleEditCancel}
          />
          {totalPages > 0 ? (
            <div className="pagination">
              <button
                className="button button--secondary"
                disabled={page <= 1 || ordersLoading}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                type="button"
              >
                Previous
              </button>
              <span className="pagination__info">
                Page {page} of {totalPages} · {totalCount} {totalCount === 1 ? "order" : "orders"}
              </span>
              <button
                className="button button--secondary"
                disabled={page >= totalPages || ordersLoading}
                onClick={() => setPage((current) => current + 1)}
                type="button"
              >
                Next
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
