"use client";

import { useEffect, useState } from "react";
import { ErrorBanner } from "@/components/error-banner";
import { listAccounts, listCashLedger, listSnapshots, listTrades } from "@/lib/api-client";
import type { Account, CashLedgerEntry, Snapshot, Trade } from "@/lib/types";
import { AnalyticsSummary } from "./analytics-summary";
import { AnalyticsCashLedgerTable, AnalyticsTradeTable, SnapshotTable } from "./analytics-tables";
import { AssetChart } from "./asset-chart";

export function AnalyticsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [cashLedger, setCashLedger] = useState<CashLedgerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadAccountData(accountId: number, clearExisting = false) {
    setError(null);
    if (clearExisting) {
      setSnapshots([]);
      setTrades([]);
      setCashLedger([]);
    }
    const [nextSnapshots, nextTrades, nextCashLedger] = await Promise.allSettled([
      listSnapshots(accountId),
      listTrades(accountId),
      listCashLedger(accountId)
    ]);

    if (nextSnapshots.status === "fulfilled") {
      setSnapshots(nextSnapshots.value);
    }
    if (nextTrades.status === "fulfilled") {
      setTrades(nextTrades.value);
    }
    if (nextCashLedger.status === "fulfilled") {
      setCashLedger(nextCashLedger.value);
    }

    const failed = [nextSnapshots, nextTrades, nextCashLedger].find((result) => result.status === "rejected");
    if (failed?.status === "rejected") {
      setError(failed.reason instanceof Error ? failed.reason.message : "Some analytics panels failed to load");
    }
  }

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const nextAccounts = await listAccounts();
        setAccounts(nextAccounts);
        const firstAccountId = nextAccounts[0]?.id ?? null;
        setSelectedAccountId(firstAccountId);
        if (firstAccountId) {
          await loadAccountData(firstAccountId, true);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load analytics data");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  const latestSnapshot = snapshots.reduce<Snapshot | null>((latest, snapshot) => {
    if (!latest || snapshot.trade_date > latest.trade_date) {
      return snapshot;
    }
    return latest;
  }, null);

  return (
    <section className="page">
      <div className="page__header">
        <div>
          <h1>Analytics</h1>
          <p className="muted">Review account snapshots, trades, and cash movements.</p>
        </div>
        <label>
          Account
          <select
            disabled={accounts.length === 0}
            value={selectedAccountId ?? ""}
            onChange={(event) => {
              const accountId = Number(event.target.value);
              setSelectedAccountId(accountId);
              void loadAccountData(accountId, true);
            }}
          >
            {accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
          </select>
        </label>
      </div>
      {loading ? <div className="panel">Loading paper trading data...</div> : null}
      {!loading && accounts.length === 0 ? <div className="panel">No paper accounts yet. Create an account before viewing analytics.</div> : null}
      {error ? <ErrorBanner message={error} /> : null}
      <AnalyticsSummary snapshot={latestSnapshot} />
      <section className="panel">
        <div className="panel__header"><h2>Total Assets</h2></div>
        <AssetChart snapshots={snapshots} />
      </section>
      <section className="panel"><h2>Snapshots</h2><SnapshotTable snapshots={snapshots} /></section>
      <section className="panel"><h2>Trades</h2><AnalyticsTradeTable trades={trades} /></section>
      <section className="panel"><h2>Cash Ledger</h2><AnalyticsCashLedgerTable entries={cashLedger} /></section>
    </section>
  );
}
