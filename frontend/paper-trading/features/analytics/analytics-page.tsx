"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ErrorBanner } from "@/components/error-banner";
import { getAnalytics, listAccounts } from "@/lib/api-client";
import type { Account, AnalyticsResponse } from "@/lib/types";
import { AnalyticsSummary } from "./analytics-summary";
import { AssetChart } from "./asset-chart";
import {
  AnalyticsActivitySection,
  AnalyticsCorporateActionsSection,
  AnalyticsExecutionSection,
  AnalyticsRiskSection,
  AnalyticsTradeQualitySection,
  ValuationGapsSection
} from "./analytics-tables";

export function AnalyticsPage() {
  const searchParams = useSearchParams();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [analytics, setAnalytics] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  async function loadAccountData(accountId: number, clearExisting = false) {
    const requestId = ++requestIdRef.current;
    setError(null);
    if (clearExisting) {
      setAnalytics(null);
    }
    const [nextAnalytics] = await Promise.allSettled([getAnalytics(accountId)]);

    if (requestId !== requestIdRef.current) {
      return;
    }

    if (nextAnalytics.status === "fulfilled") {
      setAnalytics(nextAnalytics.value);
    }

    const failed = [nextAnalytics].find((result) => result.status === "rejected");
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
        {analytics?.available === false ? (
          <div className="empty-state">
            <strong>Performance analytics unavailable</strong>
            <br />
            {analytics.reason.replaceAll("_", " ")} - repair the account or resolve the valuation gaps before viewing performance.
          </div>
        ) : null}
        {analytics?.available ? <AnalyticsSummary analytics={analytics} /> : null}
        {analytics?.available ? <AssetChart events={analytics.event_series} /> : null}
      </section>
      {analytics?.valuation_gaps?.length ? (
        <section className="panel">
          <h2>Valuation Gaps</h2>
          <ValuationGapsSection gaps={analytics.valuation_gaps} />
        </section>
      ) : null}
      {analytics?.available !== false ? (
        <>
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
            <AnalyticsRiskSection analytics={analytics} />
          </section>
          <section className="panel">
            <h2>Corporate Action Audit</h2>
            <AnalyticsCorporateActionsSection analytics={analytics} />
          </section>
        </>
      ) : null}
    </section>
  );
}
