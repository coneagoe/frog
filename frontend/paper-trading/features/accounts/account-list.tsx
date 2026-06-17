import Link from "next/link";
import { DataTable, type Column } from "@/components/data-table";
import { MoneyText } from "@/components/money-text";
import { StatusBadge } from "@/components/status-badge";
import type { Account } from "@/lib/types";

const accountColumns: Column<Account>[] = [
  { key: "name", header: "Name", render: (account) => account.name },
  { key: "initial_cash", header: "Initial Cash", align: "right", render: (account) => <MoneyText value={account.initial_cash} /> },
  { key: "status", header: "Status", render: (account) => <StatusBadge value={account.status} /> },
  { key: "currency", header: "Currency", render: (account) => account.base_currency },
  {
    key: "actions",
    header: "Actions",
    render: (account) => (
      <div className="actions">
        <Link href={`/trade?accountId=${account.id}`}>Trade</Link>
        <Link href={`/analytics?accountId=${account.id}`}>Analytics</Link>
      </div>
    )
  }
];

export function AccountList({ accounts }: { accounts: Account[] }) {
  return <DataTable columns={accountColumns} emptyTitle="No paper accounts yet" getRowKey={(account) => account.id} rows={accounts} />;
}
