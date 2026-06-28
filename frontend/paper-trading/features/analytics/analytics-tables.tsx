import type { ReactNode } from "react";
import { DataTable, type Column } from "@/components/data-table";
import { MoneyText } from "@/components/money-text";
import { formatDate, formatPercent, formatQuantity, labelStatus } from "@/lib/format";
import type { ActivityBucket, AnalyticsResponse, RoundTrip, Snapshot } from "@/lib/types";
import { MetricValueText } from "./analytics-summary";
import { AssetChart } from "./asset-chart";

function MetricCard({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="panel metric-card">
      <span className="muted">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ActivityTable({ title, rows }: { title: string; rows: ActivityBucket[] }) {
  const columns: Column<ActivityBucket>[] = [
    { key: "period", header: "Period", render: (row) => row.period },
    { key: "orders", header: "Orders", align: "right", render: (row) => formatQuantity(row.order_count) },
    { key: "trades", header: "Trades", align: "right", render: (row) => formatQuantity(row.trade_count) },
    { key: "filled", header: "Filled", align: "right", render: (row) => formatQuantity(row.filled_count) },
    { key: "rejected", header: "Rejected", align: "right", render: (row) => formatQuantity(row.rejected_count) }
  ];

  return <DataTable columns={columns} emptyTitle={`No ${title.toLowerCase()} activity yet`} getRowKey={(row) => row.period} rows={rows} />;
}

function RoundTripTable({ rows }: { rows: RoundTrip[] }) {
  const columns: Column<RoundTrip>[] = [
    { key: "symbol", header: "Symbol", render: (row) => row.symbol },
    { key: "open", header: "Opened", render: (row) => formatDate(row.open_trade_date) },
    { key: "close", header: "Closed", render: (row) => formatDate(row.close_trade_date) },
    { key: "entry", header: "Entry", align: "right", render: (row) => <MoneyText value={row.entry_amount} /> },
    { key: "exit", header: "Exit", align: "right", render: (row) => <MoneyText value={row.exit_amount} /> },
    { key: "fees", header: "Fees", align: "right", render: (row) => <MoneyText value={row.fees} /> },
    { key: "pnl", header: "Realized PnL", align: "right", render: (row) => <MoneyText value={row.realized_pnl} /> },
    { key: "return", header: "Return", align: "right", render: (row) => formatPercent(row.return_pct) },
    { key: "holding", header: "Days", align: "right", render: (row) => formatQuantity(row.holding_days) },
    { key: "status", header: "Status", render: (row) => labelStatus(row.status) }
  ];

  return <DataTable columns={columns} emptyTitle="No round trips yet" getRowKey={(row) => row.id} rows={rows} />;
}

export function AnalyticsActivitySection({ analytics }: { analytics: AnalyticsResponse | null }) {
  return (
    <div className="grid grid--two">
      <ActivityTable rows={analytics?.activity_daily ?? []} title="Daily" />
      <ActivityTable rows={analytics?.activity_weekly ?? []} title="Weekly" />
      <div style={{ gridColumn: "1 / -1" }}>
        <ActivityTable rows={analytics?.activity_monthly ?? []} title="Monthly" />
      </div>
    </div>
  );
}

export function AnalyticsExecutionSection({ analytics }: { analytics: AnalyticsResponse | null }) {
  const execution = analytics?.execution;

  return (
    <>
      <div className="summary-grid">
        <MetricCard label="Submitted Orders" value={execution?.order_count ?? 0} />
        <MetricCard label="Filled Orders" value={execution?.filled_count ?? 0} />
        <MetricCard label="Rejected Orders" value={execution?.rejected_count ?? 0} />
        <MetricCard label="Fill Rate" value={<MetricValueText metric={execution?.fill_rate} percent />} />
        <MetricCard label="Rejection Rate" value={<MetricValueText metric={execution?.rejection_rate} percent />} />
      </div>
      <h3>Reject Reasons</h3>
      <DataTable
        columns={[
          { key: "reason", header: "Reason", render: (row: { reason: string; count: number }) => row.reason },
          { key: "count", header: "Count", align: "right", render: (row: { reason: string; count: number }) => formatQuantity(row.count) }
        ]}
        emptyTitle="No reject reasons yet"
        getRowKey={(row) => row.reason}
        rows={execution?.reject_reasons ?? []}
      />
    </>
  );
}

export function AnalyticsTradeQualitySection({ analytics }: { analytics: AnalyticsResponse | null }) {
  const tradeQuality = analytics?.trade_quality;

  return (
    <>
      <div className="summary-grid">
        <MetricCard label="Closed Round Trips" value={tradeQuality?.closed_count ?? 0} />
        <MetricCard label="Win Rate" value={<MetricValueText metric={tradeQuality?.win_rate} percent />} />
        <MetricCard label="Avg Win" value={<MetricValueText metric={tradeQuality?.avg_win} />} />
        <MetricCard label="Avg Loss" value={<MetricValueText metric={tradeQuality?.avg_loss} />} />
        <MetricCard label="Payoff Ratio" value={<MetricValueText metric={tradeQuality?.payoff_ratio} />} />
        <MetricCard label="Profit Factor" value={<MetricValueText metric={tradeQuality?.profit_factor} />} />
        <MetricCard label="Consecutive Wins" value={tradeQuality?.consecutive_wins ?? 0} />
        <MetricCard label="Consecutive Losses" value={tradeQuality?.consecutive_losses ?? 0} />
        <MetricCard label="Avg Holding Days" value={<MetricValueText metric={tradeQuality?.avg_holding_days} />} />
      </div>
      <h3>Round Trips</h3>
      <RoundTripTable rows={tradeQuality?.round_trips ?? []} />
    </>
  );
}

export function AnalyticsRiskSection({ analytics, snapshots }: { analytics: AnalyticsResponse | null; snapshots: Snapshot[] }) {
  const risk = analytics?.risk;

  return (
    <>
      <div className="summary-grid">
        <MetricCard label="Max Drawdown" value={<MetricValueText metric={risk?.max_drawdown} percent />} />
        <MetricCard label="Current Drawdown" value={<MetricValueText metric={risk?.current_drawdown} percent />} />
        <MetricCard label="Sharpe" value={<MetricValueText metric={risk?.sharpe} />} />
        <MetricCard label="Sortino" value={<MetricValueText metric={risk?.sortino} />} />
        <MetricCard label="Calmar" value={<MetricValueText metric={risk?.calmar} />} />
      </div>
      <AssetChart snapshots={snapshots} />
    </>
  );
}
