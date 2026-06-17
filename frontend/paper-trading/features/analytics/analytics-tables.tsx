import { DataTable, type Column } from "@/components/data-table";
import { MoneyText } from "@/components/money-text";
import { formatDate, formatQuantity } from "@/lib/format";
import type { CashLedgerEntry, Snapshot, Trade } from "@/lib/types";

export function SnapshotTable({ snapshots }: { snapshots: Snapshot[] }) {
  const columns: Column<Snapshot>[] = [
    { key: "date", header: "Date", render: (row) => formatDate(row.trade_date) },
    { key: "total", header: "Total Assets", align: "right", render: (row) => <MoneyText value={row.total_assets} /> },
    { key: "cash", header: "Cash", align: "right", render: (row) => <MoneyText value={row.cash_available} /> },
    { key: "market", header: "Market Value", align: "right", render: (row) => <MoneyText value={row.market_value} /> },
    { key: "realized", header: "Realized PnL", align: "right", render: (row) => <MoneyText value={row.realized_pnl} /> },
    { key: "unrealized", header: "Unrealized PnL", align: "right", render: (row) => <MoneyText value={row.unrealized_pnl} /> }
  ];
  return <DataTable columns={columns} emptyTitle="No snapshots yet" getRowKey={(row) => row.id} rows={snapshots} />;
}

export function AnalyticsTradeTable({ trades }: { trades: Trade[] }) {
  const columns: Column<Trade>[] = [
    { key: "date", header: "Date", render: (row) => formatDate(row.trade_date) },
    { key: "symbol", header: "Symbol", render: (row) => row.symbol },
    { key: "side", header: "Side", render: (row) => row.side.toUpperCase() },
    { key: "quantity", header: "Qty", align: "right", render: (row) => formatQuantity(row.quantity) },
    { key: "price", header: "Price", align: "right", render: (row) => <MoneyText value={row.price} /> },
    { key: "amount", header: "Amount", align: "right", render: (row) => <MoneyText value={row.amount} /> }
  ];
  return <DataTable columns={columns} emptyTitle="No trades" getRowKey={(row) => row.id} rows={trades} />;
}

export function AnalyticsCashLedgerTable({ entries }: { entries: CashLedgerEntry[] }) {
  const columns: Column<CashLedgerEntry>[] = [
    { key: "event", header: "Event", render: (row) => row.event_type },
    { key: "amount", header: "Amount", align: "right", render: (row) => <MoneyText value={row.amount} /> },
    { key: "note", header: "Note", render: (row) => row.note ?? "-" }
  ];
  return <DataTable columns={columns} emptyTitle="No cash ledger entries" getRowKey={(row) => row.id} rows={entries} />;
}
