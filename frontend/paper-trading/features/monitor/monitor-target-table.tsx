import type { MonitorTarget } from "@/lib/types";

type Props = {
  targets: MonitorTarget[];
  busyTargetIds: ReadonlySet<number>;
  managementMode: boolean;
  loading: boolean;
  page: number;
  totalCount: number;
  totalPages: number;
  sort: string;
  onSort: () => void;
  onPreviousPage: () => void;
  onNextPage: () => void;
  onEdit: (target: MonitorTarget) => void;
  onToggle: (target: MonitorTarget) => void;
  onDelete: (target: MonitorTarget) => void;
};

function Pagination({
  disabled,
  page,
  totalCount,
  totalPages,
  onPrevious,
  onNext,
}: {
  disabled: boolean;
  page: number;
  totalCount: number;
  totalPages: number;
  onPrevious: () => void;
  onNext: () => void;
}) {
  return (
    <nav aria-label="Pagination" className="pagination">
      <button className="button button--secondary" disabled={disabled || page <= 1} type="button" onClick={onPrevious}>
        Previous
      </button>
      <span className="pagination__info">Page {page} of {totalPages} · {totalCount} items</span>
      <button className="button button--secondary" disabled={disabled || page >= totalPages} type="button" onClick={onNext}>
        Next
      </button>
    </nav>
  );
}

export function MonitorTargetTable({
  targets,
  busyTargetIds,
  managementMode,
  loading,
  page,
  totalCount,
  totalPages,
  sort,
  onSort,
  onPreviousPage,
  onNextPage,
  onEdit,
  onToggle,
  onDelete,
}: Props) {
  if (!targets.length) return null;
  const sortLabel = sort === "stock_code_asc" ? "ascending" : sort === "stock_code_desc" ? "descending" : "none";

  return (
    <>
      <div className="table-wrap">
        <table className="table table--compact">
          <thead>
            <tr>
              <th aria-sort={sortLabel}>
                <button className="table__sort-button" disabled={loading} type="button" onClick={onSort}>
                  Target {sort === "stock_code_asc" ? "↑" : sort === "stock_code_desc" ? "↓" : ""}
                </button>
              </th>
              <th>Scope</th>
              <th>Condition</th>
              <th>Status</th>
              <th>Owner</th>
              <th>Note</th>
              {managementMode ? <th>Actions</th> : null}
            </tr>
          </thead>
          <tbody>
            {targets.map((target) => {
              const operationalState = target.operational_state ?? (target.enabled ? "running" : "disabled");
              const triggeredMarker = target.last_state ? "Triggered" : "Not triggered";
              return (
                <tr key={target.id}>
                  <td>
                    <strong>{target.stock_code}</strong> <span className="muted">{target.stock_name || "—"}</span>
                  </td>
                  <td>{target.market} · {target.frequency}</td>
                  <td>
                    {target.condition
                      ? `${target.condition.type.replaceAll("_", " ")} · ${target.condition.direction}`
                      : "Workflow"}
                  </td>
                  <td>
                    <span className={`status-badge ${operationalState === "running" ? "status-badge--active" : ""}`}>
                      {operationalState[0].toUpperCase() + operationalState.slice(1)}
                    </span>
                    <span className="muted"> · {triggeredMarker}</span>
                  </td>
                  <td>{target.workflow ?? (target.target_type === "workflow" ? "Workflow" : "Manual")}</td>
                  <td>{target.note || <span className="muted">—</span>}</td>
                  {managementMode ? (
                    <td>
                      {target.can_manage ? (
                        <div className="actions monitor-actions">
                          <button aria-label={`Edit ${target.stock_code}`} className="button button--secondary" disabled={busyTargetIds.has(target.id) || loading} type="button" onClick={() => onEdit(target)}>
                            Edit
                          </button>
                          <button aria-label={`${target.enabled ? "Disable" : "Enable"} ${target.stock_code}`} className="button button--secondary" disabled={busyTargetIds.has(target.id) || loading} type="button" onClick={() => onToggle(target)}>
                            {target.enabled ? "Disable" : "Enable"}
                          </button>
                          <button aria-label={`Delete ${target.stock_code}`} className="button button--secondary" disabled={busyTargetIds.has(target.id) || loading} type="button" onClick={() => onDelete(target)}>
                            Delete
                          </button>
                        </div>
                      ) : <span className="muted">Read-only</span>}
                    </td>
                  ) : null}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {totalPages > 1 ? <Pagination disabled={loading} page={page} totalCount={totalCount} totalPages={totalPages} onNext={onNextPage} onPrevious={onPreviousPage} /> : null}
    </>
  );
}
