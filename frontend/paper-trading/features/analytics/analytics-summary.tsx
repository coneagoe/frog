import { MoneyText } from "@/components/money-text";
import { formatPercent } from "@/lib/format";
import type { AnalyticsResponse, MetricValue, Snapshot } from "@/lib/types";

export function MetricValueText({ metric, percent = false }: { metric: MetricValue | null | undefined; percent?: boolean }) {
  if (!metric || metric.value === null || metric.value === undefined || metric.value === "") {
    return <span>{metric?.reason ?? "-"}</span>;
  }

  return <span>{percent ? formatPercent(metric.value) : metric.value}</span>;
}

export function AnalyticsSummary({ analytics, snapshot }: { analytics: AnalyticsResponse | null; snapshot: Snapshot | null }) {
  const overview = analytics?.overview;
  const cards = [
    ["Total Assets", <MoneyText value={overview?.total_assets ?? snapshot?.total_assets} />],
    ["Cash Available", <MoneyText value={overview?.cash_available ?? snapshot?.cash_available} />],
    ["Cash Frozen", <MoneyText value={snapshot?.cash_frozen} />],
    ["Market Value", <MoneyText value={overview?.market_value ?? snapshot?.market_value} />],
    ["Realized PnL", <MoneyText value={overview?.realized_pnl ?? snapshot?.realized_pnl} />],
    ["Unrealized PnL", <MoneyText value={overview?.unrealized_pnl ?? snapshot?.unrealized_pnl} />],
    ["Total Return", <MetricValueText metric={overview?.total_return} percent />]
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
