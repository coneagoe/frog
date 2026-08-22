"use client";

import { useMemo, useState, type ReactNode } from "react";
import { EmptyState } from "./empty-state";

export type SortDirection = "asc" | "desc";

export type Column<T> = {
  key: string;
  header: string;
  align?: "left" | "right";
  render: (row: T) => ReactNode;
  sortValue?: (row: T) => string | number | null | undefined;
};

type SortState = {
  key: string;
  direction: SortDirection;
};

function isMissingSortValue(value: string | number | null | undefined): boolean {
  return value === null || value === undefined || value === "";
}

export function compareSortValues(
  left: string | number | null | undefined,
  right: string | number | null | undefined,
  direction: SortDirection
): number {
  const leftMissing = isMissingSortValue(left);
  const rightMissing = isMissingSortValue(right);
  if (leftMissing || rightMissing) {
    if (leftMissing && rightMissing) {
      return 0;
    }
    return leftMissing ? 1 : -1;
  }
  const result =
    typeof left === "number" && typeof right === "number"
      ? left - right
      : String(left).localeCompare(String(right), "zh-CN", { numeric: true, sensitivity: "base" });
  return direction === "asc" ? result : -result;
}

function nextSortState(current: SortState | null, key: string): SortState | null {
  if (current?.key !== key) {
    return { key, direction: "asc" };
  }
  if (current.direction === "asc") {
    return { key, direction: "desc" };
  }
  return null;
}

function sortIndicator(direction: SortDirection | undefined): string {
  if (direction === "asc") {
    return "▲";
  }
  if (direction === "desc") {
    return "▼";
  }
  return "↕";
}

export function DataTable<T>({
  columns,
  getRowKey,
  rows,
  emptyTitle,
  density = "default"
}: {
  columns: Column<T>[];
  getRowKey: (row: T) => string | number;
  rows: T[];
  emptyTitle: string;
  density?: "default" | "compact";
}) {
  const [sort, setSort] = useState<SortState | null>(null);

  const sortedRows = useMemo(() => {
    if (!sort) {
      return rows;
    }
    const column = columns.find((item) => item.key === sort.key);
    if (!column?.sortValue) {
      return rows;
    }
    const sortValue = column.sortValue;
    return [...rows].sort((left, right) => compareSortValues(sortValue(left), sortValue(right), sort.direction));
  }, [columns, rows, sort]);

  if (rows.length === 0) {
    return <EmptyState title={emptyTitle} />;
  }

  const isCompact = density === "compact";
  return (
    <div className={isCompact ? "table-wrap table-wrap--compact" : "table-wrap"}>
      <table className={isCompact ? "table table--compact" : "table"}>
        <thead>
          <tr>
            {columns.map((column) => {
              const sortable = typeof column.sortValue === "function";
              const direction = sort?.key === column.key ? sort.direction : undefined;
              const ariaSort = direction === "asc" ? "ascending" : direction === "desc" ? "descending" : "none";
              const className = [column.align === "right" ? "numeric" : undefined, sortable ? "is-sortable" : undefined]
                .filter(Boolean)
                .join(" ");
              return (
                <th aria-sort={sortable ? ariaSort : undefined} className={className || undefined} key={column.key}>
                  {sortable ? (
                    <button className="table__sort-button" onClick={() => setSort((current) => nextSortState(current, column.key))} type="button">
                      {column.header}
                      <span aria-hidden="true" className="table__sort-indicator">
                        {sortIndicator(direction)}
                      </span>
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row) => (
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
