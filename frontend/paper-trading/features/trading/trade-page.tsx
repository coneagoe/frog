"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ErrorBanner } from "@/components/error-banner";
import { listAccounts } from "@/lib/api-client";
import type { Account } from "@/lib/types";
import { OrderForm } from "./order-form";
import { PriceChart } from "./price-chart";

export function TradePage() {
  const searchParams = useSearchParams();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [symbol, setSymbol] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    const requestId = ++requestIdRef.current;
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const nextAccounts = await listAccounts();
        if (cancelled || requestId !== requestIdRef.current) return;
        setAccounts(nextAccounts);
        const requestedAccountId = Number(searchParams.get("accountId"));
        const firstAccountId = nextAccounts.some((account) => account.id === requestedAccountId)
          ? requestedAccountId
          : nextAccounts[0]?.id ?? null;
        setSelectedAccountId(firstAccountId);
      } catch (err) {
        if (!cancelled && requestId === requestIdRef.current) {
          setError(err instanceof Error ? err.message : "Failed to load trading data");
        }
      } finally {
        if (!cancelled && requestId === requestIdRef.current) {
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
          <h1>Trade</h1>
          <p className="muted">Submit paper orders.</p>
        </div>
        <label>
          <span className="account-selector">
            Account
            <select
              value={selectedAccountId ?? ""}
              onChange={(event) => {
                setSelectedAccountId(Number(event.target.value));
              }}
            >
              {accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
            </select>
          </span>
        </label>
      </div>
      {loading ? <div className="panel">Loading paper trading data...</div> : null}
      {!loading && accounts.length === 0 ? <div className="panel">No paper accounts yet. Create an account before trading.</div> : null}
      {error ? <ErrorBanner message={error} /> : null}
      <div className="grid grid--trade">
        <div className="grid chart-workspace">
          <div className="panel__header chart-workspace__toolbar">
            <label className="form">
              Chart symbol
              <input aria-label="Chart symbol" value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} />
            </label>
          </div>
          <PriceChart symbol={symbol} />
        </div>
        <div className="grid">
          <OrderForm accounts={accounts} selectedAccountId={selectedAccountId} onSubmitted={() => undefined} />
        </div>
      </div>
    </section>
  );
}
