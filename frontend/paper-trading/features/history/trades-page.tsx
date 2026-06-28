"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ErrorBanner } from "@/components/error-banner";
import { listAccounts, listTrades } from "@/lib/api-client";
import type { Account, Trade } from "@/lib/types";
import { TradeTable } from "@/features/trading/trading-tables";

export function TradesPage() {
  const searchParams = useSearchParams();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  async function loadTrades(accountId: number) {
    const requestId = ++requestIdRef.current;
    setTrades([]);
    setError(null);
    try {
      const nextTrades = await listTrades(accountId);
      if (requestId === requestIdRef.current) {
        setTrades(nextTrades);
      }
    } catch (err) {
      if (requestId === requestIdRef.current) {
        setError(err instanceof Error ? err.message : "Failed to load trades");
      }
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const nextAccounts = await listAccounts();
        if (cancelled) return;
        setAccounts(nextAccounts);
        const requestedAccountId = Number(searchParams.get("accountId"));
        const firstAccountId = nextAccounts.some((account) => account.id === requestedAccountId)
          ? requestedAccountId
          : nextAccounts[0]?.id ?? null;
        setSelectedAccountId(firstAccountId);
        if (firstAccountId) {
          await loadTrades(firstAccountId);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load trades data");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [searchParams]);

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
              onChange={(event) => {
                const accountId = Number(event.target.value);
                setSelectedAccountId(accountId);
                void loadTrades(accountId);
              }}
            >
              {accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
            </select>
          </span>
        </label>
      </div>
      {loading ? <div className="panel">Loading trades...</div> : null}
      {!loading && accounts.length === 0 ? <div className="panel">No paper accounts yet. Create an account before viewing trades.</div> : null}
      {error ? <ErrorBanner message={error} /> : null}
      <TradeTable trades={trades} />
    </section>
  );
}
