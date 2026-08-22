import { useEffect, useState, type ReactNode } from "react";
import { EmptyState } from "./empty-state";

export type SortValue = string | number | null | undefined;

export type Column<T> = {
  key: string;
  header: string;
  align?: "left" | "right";
  render: (row: T) => ReactNode;
  sortable?: (row: T) => SortValue;
};

type SortDirection = "asc" | "desc";
type SortState = { key: string; direction: SortDirection } | null;

function sortableValue(value: SortValue): { valid: boolean; value: string | number } {
  if (value === null || value === undefined) return { valid: false, value: "" };
  if (typeof value === "number") return Number.isFinite(value) ? { valid: true, value } : { valid: false, value: "" };
  const trimmed = value.trim();
  return trimmed ? { valid: true, value: trimmed.toLocaleLowerCase() } : { valid: false, value: "" };
}

function compareValues<T>(column: Column<T>, left: T, right: T, direction: SortDirection): number {
  const leftValue = sortableValue(column.sortable?.(left));
  const rightValue = sortableValue(column.sortable?.(right));
  if (leftValue.valid !== rightValue.valid) return leftValue.valid ? -1 : 1;
  if (!leftValue.valid) return 0;
  const comparison = leftValue.value < rightValue.value ? -1 : leftValue.value > rightValue.value ? 1 : 0;
  return direction === "asc" ? comparison : -comparison;
}

export function DataTable<T>({
  columns,
  getRowKey,
  rows,
  emptyTitle,
  density = "default",
  resetKey
}: {
  columns: Column<T>[];
  getRowKey: (row: T) => string | number;
  rows: T[];
  emptyTitle: string;
  density?: "default" | "compact";
  resetKey?: unknown;
}) {
  const [sort, setSort] = useState<SortState>(null);

  useEffect(() => {
    setSort(null);
  }, [resetKey]);

  const activeColumn = sort ? columns.find((column) => column.key === sort.key) : undefined;
  const displayRows = activeColumn && sort ? [...rows].sort((left, right) => compareValues(activeColumn, left, right, sort.direction)) : rows;

  if (rows.length === 0) {
    return <EmptyState title={emptyTitle} />;
  }
  const isCompact = density === "compact";
  return (
    <div className={isCompact ? "table-wrap table-wrap--compact" : "table-wrap"}>
      <table className={isCompact ? "table table--compact" : "table"}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                aria-sort={sort?.key === column.key ? (sort.direction === "asc" ? "ascending" : "descending") : undefined}
                className={column.align === "right" ? "numeric" : undefined}
                key={column.key}
              >
                {column.sortable ? (
                  <button
                    className="table__sort-button"
                    onClick={() => setSort((current) => ({
                      key: column.key,
                      direction: current?.key === column.key && current.direction === "asc" ? "desc" : "asc"
                    }))}
                    type="button"
                  >
                    {column.header}
                    {sort?.key === column.key ? <span aria-hidden="true" className="table__sort-indicator">{sort.direction === "asc" ? "↑" : "↓"}</span> : null}
                  </button>
                ) : column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {displayRows.map((row) => (
            <tr key={getRowKey(row)}>
              {columns.map((column) => (
                <td className={column.align === "right" ? "numeric" : undefined} key={column.key}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
