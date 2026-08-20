"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorBanner } from "@/components/error-banner";
import { listAccounts, listTrades } from "@/lib/api-client";
import type { Account, Trade, TradePage } from "@/lib/types";
import { TradeTable } from "@/features/trading/trading-tables";

const PAGE_SIZE = 25;
const SHANGHAI_TIME_ZONE = "Asia/Shanghai";
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
export type RangePreset = "today" | "7d" | "30d";
type TradesQuery = {
  accountId: number | null;
  startDate: string;
  endDate: string;
  page: number;
};
type SearchParamsLike = { get(name: string): string | null };

export function shanghaiToday(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: SHANGHAI_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const part = (type: string) =>
    parts.find((entry) => entry.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

export function shiftDate(date: string, days: number): string {
  const [year, month, day] = date.split("-").map(Number);
  const shifted = new Date(Date.UTC(year, month - 1, day + days));
  return `${shifted.getUTCFullYear()}-${String(shifted.getUTCMonth() + 1).padStart(2, "0")}-${String(shifted.getUTCDate()).padStart(2, "0")}`;
}

export function presetRange(preset: RangePreset): [string, string] {
  const today = shanghaiToday();
  if (preset === "today") return [today, today];
  return [shiftDate(today, preset === "7d" ? -6 : -29), today];
}

function isValidDateString(value: string): boolean {
  if (!DATE_PATTERN.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  );
}

function isValidRange(startDate: string, endDate: string): boolean {
  return (
    isValidDateString(startDate) &&
    isValidDateString(endDate) &&
    startDate <= endDate
  );
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

function parseTradesQuery(searchParams: SearchParamsLike): TradesQuery {
  const start = searchParams.get("start_date");
  const end = searchParams.get("end_date");
  const urlRange =
    start !== null && end !== null && isValidRange(start, end)
      ? { start, end }
      : null;
  const [defaultStart, defaultEnd] = presetRange("30d");
  return {
    accountId: parseAccountId(searchParams.get("accountId")),
    startDate: urlRange?.start ?? defaultStart,
    endDate: urlRange?.end ?? defaultEnd,
    page: parsePage(searchParams.get("page")),
  };
}

function activePresetFor(
  startDate: string,
  endDate: string,
): RangePreset | null {
  const today = shanghaiToday();
  if (startDate === today && endDate === today) return "today";
  if (startDate === shiftDate(today, -6) && endDate === today) return "7d";
  if (startDate === shiftDate(today, -29) && endDate === today) return "30d";
  return null;
}

const PRESETS: { key: RangePreset; label: string }[] = [
  { key: "today", label: "Today" },
  { key: "7d", label: "Last 7 days" },
  { key: "30d", label: "Last 30 days" },
];

export function TradesPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const initialQueryRef = useRef<TradesQuery | null>(null);
  if (initialQueryRef.current === null)
    initialQueryRef.current = parseTradesQuery(searchParams);
  const initialQuery = initialQueryRef.current;
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(
    null,
  );
  const [startDate, setStartDate] = useState(initialQuery.startDate);
  const [endDate, setEndDate] = useState(initialQuery.endDate);
  const [page, setPage] = useState(initialQuery.page);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [tradesLoading, setTradesLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);
  const rangeValid = isValidRange(startDate, endDate);
  const activePreset = activePresetFor(startDate, endDate);

  const loadTrades = useCallback(
    async (
      accountId: number,
      rangeStart: string,
      rangeEnd: string,
      targetPage: number,
    ): Promise<TradePage | null> => {
      const requestId = ++requestIdRef.current;
      setTrades([]);
      setTradesLoading(true);
      setError(null);
      try {
        const result = await listTrades(accountId, {
          start_date: rangeStart,
          end_date: rangeEnd,
          page: targetPage,
          page_size: PAGE_SIZE,
        });
        if (requestId === requestIdRef.current) {
          setTrades(result.items);
          setTotalCount(result.total_count);
          setTotalPages(result.total_pages);
          if (result.page !== targetPage) setPage(result.page);
          return result;
        }
      } catch (err) {
        if (requestId === requestIdRef.current)
          setError(
            err instanceof Error ? err.message : "Failed to load trades",
          );
      } finally {
        if (requestId === requestIdRef.current) {
          setTradesLoading(false);
          setLoading(false);
        }
      }
      return null;
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const nextAccounts = await listAccounts();
        if (cancelled) return;
        setAccounts(nextAccounts);
        const requestedAccountId = initialQueryRef.current?.accountId ?? null;
        const firstAccountId = nextAccounts.some(
          (account) => account.id === requestedAccountId,
        )
          ? requestedAccountId
          : (nextAccounts[0]?.id ?? null);
        setSelectedAccountId(firstAccountId);
        if (firstAccountId === null) setLoading(false);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load trades data",
          );
          setLoading(false);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (selectedAccountId === null) return;
    if (!rangeValid) {
      requestIdRef.current += 1;
      setLoading(false);
      setTradesLoading(false);
      return;
    }
    void loadTrades(selectedAccountId, startDate, endDate, page);
  }, [selectedAccountId, startDate, endDate, page, rangeValid, loadTrades]);

  useEffect(() => {
    if (selectedAccountId === null || !rangeValid) return;
    const params = new URLSearchParams({
      accountId: String(selectedAccountId),
      start_date: startDate,
      end_date: endDate,
      page: String(page),
    });
    router.replace(`/trades?${params.toString()}`);
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
  const showTradesLoading = loading || tradesLoading;

  return (
    <section className="page">
      <div className="page__header">
        <div>
          <h1>Trades</h1>
          <p className="muted">Review historical paper executions.</p>
        </div>
        <label>
          <span className="account-selector">
            Account
            <select
              disabled={accounts.length === 0}
              value={selectedAccountId ?? ""}
              onChange={(event) =>
                handleAccountChange(Number(event.target.value))
              }
            >
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </select>
          </span>
        </label>
      </div>
      <div className="filter-bar">
        <div className="filter-bar__presets">
          {PRESETS.map((preset) => (
            <button
              aria-pressed={activePreset === preset.key}
              className={
                activePreset === preset.key
                  ? "button"
                  : "button button--secondary"
              }
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
          <input
            type="date"
            value={startDate}
            onChange={(event) => handleStartDateChange(event.target.value)}
          />
        </label>
        <label className="filter-bar__field">
          <span>End date</span>
          <input
            type="date"
            value={endDate}
            onChange={(event) => handleEndDateChange(event.target.value)}
          />
        </label>
      </div>
      {!rangeValid ? (
        <p className="filter-error" role="alert">
          {startDate === "" || endDate === ""
            ? "Choose both a start date and an end date to apply a custom range."
            : "Start date must be on or before end date."}
        </p>
      ) : null}
      {showTradesLoading ? (
        <div className="panel">Loading trades...</div>
      ) : null}
      {!loading && accounts.length === 0 ? (
        <div className="panel">
          No paper accounts yet. Create an account before viewing trades.
        </div>
      ) : null}
      {error ? <ErrorBanner message={error} /> : null}
      {!showTradesLoading && accounts.length > 0 ? (
        <>
          <TradeTable trades={trades} />
          {totalPages > 1 ? (
            <div className="pagination">
              <button
                className="button button--secondary"
                disabled={page <= 1 || tradesLoading}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                type="button"
              >
                Previous
              </button>
              <span className="pagination__info">
                Page {page} of {totalPages} · {totalCount}{" "}
                {totalCount === 1 ? "trade" : "trades"}
              </span>
              <button
                className="button button--secondary"
                disabled={page >= totalPages || tradesLoading}
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
