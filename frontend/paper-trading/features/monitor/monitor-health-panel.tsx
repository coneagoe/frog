import { DataTable, type Column } from "@/components/data-table";
import type { MonitorOperationalState, MonitorTargetHealth, MonitorTargetHealthItem } from "@/lib/types";

const stateBadgeClass: Record<MonitorOperationalState, string> = {
  running: "status-badge--active",
  paused: "",
  disabled: "status-badge--failed"
};

function displayTime(value: string | null) {
  return value ? <time dateTime={value}>{new Date(value).toLocaleString()}</time> : <span className="muted">—</span>;
}

function latestError(target: MonitorTargetHealthItem) {
  const error = target.latest_error;
  if (!error) return <span className="muted">—</span>;
  return error.detail ? `${error.summary} — ${error.detail}` : error.summary;
}

export function MonitorHealthPanel({ health, loading }: { health: MonitorTargetHealth | null; loading: boolean }) {
  const columns: Column<MonitorTargetHealthItem>[] = [
    { key: "target", header: "Target", render: (target) => <strong>{target.stock_code}</strong> },
    { key: "scope", header: "Scope", render: (target) => `${target.market} · ${target.frequency}` },
    { key: "owner", header: "Owner", render: (target) => target.workflow ?? "Manual" },
    { key: "operational-state", header: "Operational state", render: (target) => <span className={`status-badge ${stateBadgeClass[target.operational_state]}`}>{target.operational_state[0].toUpperCase() + target.operational_state.slice(1)}</span> },
    { key: "trigger-state", header: "Trigger state", render: (target) => <span className={`status-badge ${target.last_state ? "status-badge--active" : ""}`}>{target.last_state ? "Triggered" : "Not triggered"}</span> },
    { key: "last-check", header: "Last check", render: (target) => displayTime(target.last_checked_at) },
    { key: "last-trigger", header: "Last trigger", render: (target) => displayTime(target.triggered_at) },
    { key: "latest-error", header: "Latest error", render: latestError }
  ];
  const counters = health ? [
    ["Total", health.summary.total], ["Running", health.summary.running], ["Paused", health.summary.paused], ["Disabled", health.summary.disabled], ["Triggered", health.summary.triggered], ["Daily", health.summary.daily], ["Intraday", health.summary.intraday]
  ] : [];

  return <section aria-labelledby="monitor-health-title" className="panel monitor-health-panel">
    <div className="monitor-health-heading"><div><p className="monitor-eyebrow">Read-only operations view</p><h2 id="monitor-health-title">Operational health</h2><p className="muted">A live view of every manual and workflow monitor target.</p></div>{loading ? <span className="monitor-health-loading">Updating…</span> : null}</div>
    {health ? <><div className="monitor-health-summary" aria-label="Health summary">{counters.map(([label, value]) => <div className="monitor-health-counter" key={String(label)}><span>{label}</span><strong>{value}</strong></div>)}</div><DataTable columns={columns} density="compact" emptyTitle="No monitor target health available" getRowKey={(target) => target.id} rows={health.targets} /></> : <p className="monitor-loading">Health data is not available yet.</p>}
  </section>;
}
