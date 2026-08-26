import type { ReactNode } from "react";
import { DataTable, type Column } from "@/components/data-table";
import { MoneyText } from "@/components/money-text";
import { formatBackendLabel, formatDate, formatPercent, formatQuantity, labelStatus } from "@/lib/format";
import type { ActivitySummary, AvailableAnalyticsResponse, RoundTrip } from "@/lib/types";
import { MetricValueText } from "./analytics-summary";

function MetricCard({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="panel metric-card">
      <span className="muted">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function UnavailableValue() {
  return <span className="muted">-</span>;
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

export function AnalyticsActivitySection({ analytics }: { analytics: AvailableAnalyticsResponse | null }) {
  const activity = analytics?.activity;

  if (!activity) {
    return <div className="muted">Activity unavailable</div>;
  }

  const units: { label: string; summary: ActivitySummary }[] = [
    { label: "Daily", summary: activity.daily },
    { label: "Weekly", summary: activity.weekly },
    { label: "Monthly", summary: activity.monthly }
  ];

  return (
    <>
      <div className="panel__header">
        <h3>Activity Coverage</h3>
        <span className="muted">
          <span>{formatDate(activity.coverage_start)}</span>
          {" - "}
          <span>{formatDate(activity.coverage_end)}</span>
        </span>
      </div>
      {units.map((unit) => (
        <section key={unit.label}>
          <h3>{unit.label}</h3>
          <div className="summary-grid">
            <MetricCard label="Total Orders" value={formatQuantity(Number(unit.summary.total_orders))} />
            <MetricCard label="Successful Orders" value={formatQuantity(Number(unit.summary.successful_orders))} />
            <MetricCard label="Failed Orders" value={formatQuantity(Number(unit.summary.failed_orders))} />
          </div>
        </section>
      ))}
    </>
  );
}

export function AnalyticsExecutionSection({ analytics }: { analytics: AvailableAnalyticsResponse | null }) {
  const execution = analytics?.execution;
  const hasExecution = execution !== undefined && execution !== null;

  return (
    <>
      <div className="summary-grid">
        <MetricCard label="Submitted Orders" value={hasExecution ? execution.order_count : <UnavailableValue />} />
        <MetricCard label="Filled Orders" value={hasExecution ? execution.filled_count : <UnavailableValue />} />
        <MetricCard label="Rejected Orders" value={hasExecution ? execution.rejected_count : <UnavailableValue />} />
        <MetricCard label="Fill Rate" value={<MetricValueText metric={execution?.fill_rate} percent />} />
        <MetricCard label="Rejection Rate" value={<MetricValueText metric={execution?.rejection_rate} percent />} />
      </div>
      <h3>Reject Reasons</h3>
      <DataTable
        columns={[
          { key: "reason", header: "Reason", render: (row: { reason: string; count: number }) => formatBackendLabel(row.reason) },
          { key: "count", header: "Count", align: "right", render: (row: { reason: string; count: number }) => formatQuantity(row.count) }
        ]}
        emptyTitle="No reject reasons yet"
        getRowKey={(row) => row.reason}
        rows={execution?.reject_reasons ?? []}
      />
    </>
  );
}

export function AnalyticsTradeQualitySection({ analytics }: { analytics: AvailableAnalyticsResponse | null }) {
  const tradeQuality = analytics?.trade_quality;
  const hasTradeQuality = tradeQuality !== undefined && tradeQuality !== null;

  return (
    <>
      <div className="summary-grid">
        <MetricCard label="Closed Round Trips" value={hasTradeQuality ? tradeQuality.closed_count : <UnavailableValue />} />
        <MetricCard label="Win Rate" value={<MetricValueText metric={tradeQuality?.win_rate} percent />} />
        <MetricCard
          label="Avg Win"
          value={
            tradeQuality?.avg_win?.value != null
              ? <MoneyText value={tradeQuality.avg_win.value} />
              : <MetricValueText metric={tradeQuality?.avg_win} />
          }
        />
        <MetricCard
          label="Avg Loss"
          value={
            tradeQuality?.avg_loss?.value != null
              ? <MoneyText value={tradeQuality.avg_loss.value} />
              : <MetricValueText metric={tradeQuality?.avg_loss} />
          }
        />
        <MetricCard label="Payoff Ratio" value={<MetricValueText metric={tradeQuality?.payoff_ratio} />} />
        <MetricCard label="Profit Factor" value={<MetricValueText metric={tradeQuality?.profit_factor} />} />
        <MetricCard label="Consecutive Wins" value={hasTradeQuality ? tradeQuality.consecutive_wins : <UnavailableValue />} />
        <MetricCard label="Consecutive Losses" value={hasTradeQuality ? tradeQuality.consecutive_losses : <UnavailableValue />} />
        <MetricCard label="Avg Holding Days" value={<MetricValueText metric={tradeQuality?.avg_holding_days} />} />
      </div>
      <h3>Round Trips</h3>
      <RoundTripTable rows={tradeQuality?.round_trips ?? []} />
    </>
  );
}

export function AnalyticsRiskSection({ analytics }: { analytics: AvailableAnalyticsResponse | null }) {
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
    </>
  );
}
