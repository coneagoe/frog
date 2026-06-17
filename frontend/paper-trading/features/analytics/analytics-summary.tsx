import { MoneyText } from "@/components/money-text";
import type { Snapshot } from "@/lib/types";

export function AnalyticsSummary({ snapshot }: { snapshot: Snapshot | null }) {
  const cards = [
    ["Total Assets", snapshot?.total_assets],
    ["Cash Available", snapshot?.cash_available],
    ["Cash Frozen", snapshot?.cash_frozen],
    ["Market Value", snapshot?.market_value],
    ["Realized PnL", snapshot?.realized_pnl],
    ["Unrealized PnL", snapshot?.unrealized_pnl]
  ];

  return (
    <div className="summary-grid">
      {cards.map(([label, value]) => (
        <div className="panel metric-card" key={label}>
          <span className="muted">{label}</span>
          <strong><MoneyText value={value} /></strong>
        </div>
      ))}
    </div>
  );
}
