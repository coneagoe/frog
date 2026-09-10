import { DataTable, type Column } from "@/components/data-table";
import type { MonitorTarget } from "@/lib/types";

type BusyTargetIds = ReadonlySet<number>;

const describeCondition = (target: MonitorTarget) => `${target.condition.type.replaceAll("_", " ")} · ${target.condition.direction}`;

function targetLabel(target: MonitorTarget) {
  return <><strong>{target.stock_code}</strong><span className="muted"> {target.stock_name || "—"}</span></>;
}

export function MonitorTargetTable({
  targets,
  busyTargetIds,
  managementMode,
  loading,
  page,
  totalCount,
  totalPages,
  onPreviousPage,
  onNextPage,
  onEdit,
  onToggle,
  onDelete
}: {
  targets: MonitorTarget[];
  busyTargetIds: BusyTargetIds;
  managementMode: boolean;
  loading: boolean;
  page: number;
  totalCount: number;
  totalPages: number;
  onPreviousPage: () => void;
  onNextPage: () => void;
  onEdit?: (target: MonitorTarget) => void;
  onToggle?: (target: MonitorTarget) => void;
  onDelete?: (target: MonitorTarget) => void;
}) {
  const columns: Column<MonitorTarget>[] = [
    { key: "stock", header: "Target", render: targetLabel, sortable: (target) => target.stock_code },
    { key: "scope", header: "Scope", render: (target) => `${target.market} · ${target.frequency}` },
    { key: "condition", header: "Condition", render: describeCondition },
    { key: "status", header: "Status", render: (target) => <span className={`status-badge ${target.enabled ? "status-badge--active" : ""}`}>{target.enabled ? "Enabled" : "Disabled"}</span> },
    { key: "note", header: "Note", render: (target) => target.note || <span className="muted">—</span> }
  ];

  if (managementMode && onEdit && onToggle && onDelete) {
    columns.push({
      key: "actions",
      header: "Actions",
      render: (target) => {
        const busy = busyTargetIds.has(target.id);
        return <div className="actions monitor-actions"><button className="button button--secondary" disabled={busy} type="button" onClick={() => onEdit(target)}>Edit</button><button aria-label={`${target.enabled ? "Disable" : "Enable"} ${target.stock_code}`} className="button button--secondary" disabled={busy} type="button" onClick={() => onToggle(target)}>{target.enabled ? "Disable" : "Enable"}</button><button aria-label={`Delete ${target.stock_code}`} className="button button--secondary monitor-delete" disabled={busy} type="button" onClick={() => onDelete(target)}>Delete</button></div>;
      }
    });
  }

  return <><DataTable columns={columns} density="compact" emptyTitle="No manual monitor targets yet" getRowKey={(target) => target.id} rows={targets} />{totalPages > 1 ? <Pagination disabled={loading} page={page} totalCount={totalCount} totalPages={totalPages} onNext={onNextPage} onPrevious={onPreviousPage} /> : null}</>;
}

export function Pagination({ disabled, page, totalCount, totalPages, onPrevious, onNext }: { disabled: boolean; page: number; totalCount: number; totalPages: number; onPrevious: () => void; onNext: () => void }) {
  return <nav aria-label="Pagination" className="pagination"><button className="button button--secondary" disabled={disabled || page <= 1} type="button" onClick={onPrevious}>Previous</button><span className="pagination__info">Page {page} of {totalPages} · {totalCount} items</span><button className="button button--secondary" disabled={disabled || page >= totalPages} type="button" onClick={onNext}>Next</button></nav>;
}
