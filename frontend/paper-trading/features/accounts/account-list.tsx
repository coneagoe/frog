import { DataTable, type Column } from "@/components/data-table";
import { MoneyText } from "@/components/money-text";
import { StatusBadge } from "@/components/status-badge";
import type { Account } from "@/lib/types";

const accountColumns: Column<Account>[] = [
  { key: "selected", header: "", render: () => null },
  { key: "name", header: "Name", render: (account) => account.name },
  { key: "initial_cash", header: "Initial Cash", align: "right", render: (account) => <MoneyText value={account.initial_cash} /> },
  { key: "status", header: "Status", render: (account) => <StatusBadge value={account.status} /> },
  { key: "currency", header: "Currency", render: (account) => account.base_currency },
  {
    key: "actions",
    header: "Actions",
    render: () => null
  }
];

function getAccountColumns(options: {
  onDelete?: (account: Account) => void;
  onSelect?: (account: Account) => void;
  selectedAccountId?: number | null;
}): Column<Account>[] {
  const { onDelete, onSelect, selectedAccountId } = options;
  return accountColumns.map((column) => {
    if (column.key === "selected") {
      return {
        ...column,
        render: (account) =>
          selectedAccountId === account.id ? <span className="status-badge status-badge--active">Selected</span> : null
      };
    }
    if (column.key !== "actions") {
      return column;
    }
    return {
      ...column,
      render: (account) => (
        <div className="actions">
          {onSelect ? (
            <button
              aria-label={`View ${account.name}`}
              className="button button--primary"
              onClick={() => onSelect(account)}
              type="button"
            >
              View
            </button>
          ) : null}
          {onDelete ? (
            <button
              aria-label={`Delete ${account.name}`}
              className="button button--secondary"
              onClick={() => onDelete(account)}
              type="button"
            >
              Delete
            </button>
          ) : null}
        </div>
      )
    };
  });
}

export function AccountList({
  accounts,
  selectedAccountId,
  onSelect,
  onDelete
}: {
  accounts: Account[];
  selectedAccountId?: number | null;
  onSelect?: (account: Account) => void;
  onDelete?: (account: Account) => void;
}) {
  return (
    <DataTable
      columns={getAccountColumns({ onDelete, onSelect, selectedAccountId })}
      emptyTitle="No paper accounts yet"
      getRowKey={(account) => account.id}
      rows={accounts}
    />
  );
}
