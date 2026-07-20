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
    ["Unit NAV", overview?.net_asset_value ?? snapshot?.net_asset_value ?? "-"],
    ["Share Count", overview?.share_count ?? snapshot?.share_count ?? "-"],
    ["NAV Return", <MetricValueText key="nav-return" metric={overview?.total_return} percent />],
    ["Simple Asset Return", <MetricValueText key="simple-return" metric={overview?.simple_asset_return} percent />]
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
