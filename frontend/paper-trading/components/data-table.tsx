import type { ReactNode } from "react";
import { EmptyState } from "./empty-state";

export type Column<T> = {
  key: string;
  header: string;
  align?: "left" | "right";
  render: (row: T) => ReactNode;
};

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
              <th className={column.align === "right" ? "numeric" : undefined} key={column.key}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
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
