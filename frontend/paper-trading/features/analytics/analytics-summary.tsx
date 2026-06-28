import { MoneyText } from "@/components/money-text";
import { formatBackendLabel, formatPercent } from "@/lib/format";
import type { AnalyticsResponse, MetricValue, Snapshot } from "@/lib/types";

export function MetricValueText({ metric, percent = false }: { metric: MetricValue | null | undefined; percent?: boolean }) {
  if (!metric || metric.value === null || metric.value === undefined || metric.value === "") {
    return <span>{formatBackendLabel(metric?.reason)}</span>;
  }

  return <span>{percent ? formatPercent(metric.value) : metric.value}</span>;
}

export function AnalyticsSummary({ analytics, snapshot }: { analytics: AnalyticsResponse | null; snapshot: Snapshot | null }) {
  const overview = analytics?.overview;
  const cards = [
    ["Total Assets", <MoneyText key="total-assets" value={overview?.total_assets ?? snapshot?.total_assets} />],
    ["Cash Available", <MoneyText key="cash-available" value={overview?.cash_available ?? snapshot?.cash_available} />],
    ["Cash Frozen", <MoneyText key="cash-frozen" value={snapshot?.cash_frozen} />],
    ["Market Value", <MoneyText key="market-value" value={overview?.market_value ?? snapshot?.market_value} />],
    ["Realized PnL", <MoneyText key="realized-pnl" value={overview?.realized_pnl ?? snapshot?.realized_pnl} />],
    ["Unrealized PnL", <MoneyText key="unrealized-pnl" value={overview?.unrealized_pnl ?? snapshot?.unrealized_pnl} />],
    ["Total Return", <MetricValueText key="total-return" metric={overview?.total_return} percent />]
  ] as const;

  return (
    <div className="summary-grid">
      {cards.map(([label, value]) => (
        <div className="panel metric-card" key={label}>
          <span className="muted">{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}
