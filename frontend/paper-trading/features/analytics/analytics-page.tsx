"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ErrorBanner } from "@/components/error-banner";
import { getAnalytics, listAccounts, listSnapshots } from "@/lib/api-client";
import type { Account, AnalyticsResponse, Snapshot } from "@/lib/types";
import { AnalyticsSummary } from "./analytics-summary";
import {
  AnalyticsActivitySection,
  AnalyticsExecutionSection,
  AnalyticsRiskSection,
  AnalyticsTradeQualitySection
} from "./analytics-tables";

export function AnalyticsPage() {
  const searchParams = useSearchParams();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  async function loadAccountData(accountId: number, clearExisting = false) {
    const requestId = ++requestIdRef.current;
    setError(null);
    if (clearExisting) {
      setSnapshots([]);
      setAnalytics(null);
    }
    const [nextSnapshots, nextAnalytics] = await Promise.allSettled([
      listSnapshots(accountId),
      getAnalytics(accountId)
    ]);

    if (requestId !== requestIdRef.current) {
      return;
    }

    if (nextSnapshots.status === "fulfilled") {
      setSnapshots(nextSnapshots.value);
    }
    if (nextAnalytics.status === "fulfilled") {
      setAnalytics(nextAnalytics.value);
    }

    const failed = [nextSnapshots, nextAnalytics].find((result) => result.status === "rejected");
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
        const requestedAccountId = Number(searchParams.get("accountId"));
        const firstAccountId = nextAccounts.some((account) => account.id === requestedAccountId)
          ? requestedAccountId
          : nextAccounts[0]?.id ?? null;
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
  }, [searchParams]);

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
          <span className="account-selector">
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
          </span>
        </label>
      </div>
      {loading ? <div className="panel">Loading paper trading data...</div> : null}
      {!loading && accounts.length === 0 ? <div className="panel">No paper accounts yet. Create an account before viewing analytics.</div> : null}
      {error ? <ErrorBanner message={error} /> : null}
      <section className="panel">
        <h2>Overview</h2>
        <AnalyticsSummary analytics={analytics} snapshot={latestSnapshot} />
      </section>
      <section className="panel">
        <h2>Activity</h2>
        <AnalyticsActivitySection analytics={analytics} />
      </section>
      <section className="panel">
        <h2>Execution</h2>
        <AnalyticsExecutionSection analytics={analytics} />
      </section>
      <section className="panel">
        <h2>Trade Quality</h2>
        <AnalyticsTradeQualitySection analytics={analytics} />
      </section>
      <section className="panel">
        <h2>Risk &amp; Drawdown</h2>
        <AnalyticsRiskSection analytics={analytics} snapshots={snapshots} />
      </section>
    </section>
  );
}
