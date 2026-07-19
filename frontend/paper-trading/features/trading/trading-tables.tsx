import { DataTable, type Column } from "@/components/data-table";
import { MoneyText } from "@/components/money-text";
import { StatusBadge } from "@/components/status-badge";
import { formatDate, formatQuantity } from "@/lib/format";
import type { CashLedgerEntry, Order, Position, Trade } from "@/lib/types";

export function PositionTable({ density, positions }: { density?: "default" | "compact"; positions: Position[] }) {
  const columns: Column<Position>[] = [
    { key: "symbol", header: "Symbol", render: (row) => row.symbol },
    { key: "total", header: "Total", align: "right", render: (row) => formatQuantity(row.total_quantity) },
    { key: "frozen", header: "Frozen", align: "right", render: (row) => formatQuantity(row.frozen_quantity) },
    { key: "cost", header: "Cost", align: "right", render: (row) => <MoneyText value={row.cost_amount} /> },
    { key: "pnl", header: "Realized PnL", align: "right", render: (row) => <MoneyText value={row.realized_pnl} /> }
  ];
  return <DataTable columns={columns} density={density} emptyTitle="No positions" getRowKey={(row) => row.symbol} rows={positions} />;
}

export function OrderTable({
  orders,
  onCancel,
  editingOrderId,
  editingValue,
  onEditStart,
  onEditValueChange,
  onEditSave,
  onEditCancel
}: {
  orders: Order[];
  onCancel: (orderId: number) => void;
  editingOrderId?: number | null;
  editingValue?: string;
  onEditStart?: (orderId: number) => void;
  onEditValueChange?: (value: string) => void;
  onEditSave?: (orderId: number) => void;
  onEditCancel?: () => void;
}) {
  const cancellable = new Set(["accepted", "new", "partially_filled"]);
  const canEdit = typeof onEditStart === "function";
  const columns: Column<Order>[] = [
    { key: "id", header: "ID", render: (row) => row.id },
    { key: "symbol", header: "Symbol", render: (row) => row.symbol },
    { key: "side", header: "Side", render: (row) => row.side.toUpperCase() },
    { key: "quantity", header: "Qty", align: "right", render: (row) => formatQuantity(row.quantity) },
    { key: "price", header: "Limit", align: "right", render: (row) => <MoneyText value={row.limit_price} /> },
    { key: "date", header: "Date", render: (row) => formatDate(row.trade_date) },
    { key: "status", header: "Status", render: (row) => <StatusBadge value={row.status} /> },
    {
      key: "comment",
      header: "Comment",
      render: (row) => {
        if (canEdit && editingOrderId === row.id) {
          return (
            <input
              aria-label="Edit comment"
              value={editingValue ?? ""}
              onChange={(event) => onEditValueChange?.(event.target.value)}
            />
          );
        }
        return <>{row.comment || "-"}</>;
      }
    },
    {
      key: "action",
      header: "Action",
      render: (row) => {
        if (canEdit && editingOrderId === row.id) {
          return (
            <>
              <button className="button" onClick={() => onEditSave?.(row.id)} type="button">Save</button>
              <button className="button button--secondary" onClick={() => onEditCancel?.()} type="button">Cancel</button>
            </>
          );
        }
        return (
          <>
            {cancellable.has(row.status)
              ? <button className="button button--secondary" onClick={() => onCancel(row.id)} type="button">Cancel</button>
              : null}
            {canEdit ? <button className="button button--secondary" onClick={() => onEditStart?.(row.id)} type="button">Edit</button> : null}
          </>
        );
      }
    }
  ];
  return <DataTable columns={columns} emptyTitle="No orders" getRowKey={(row) => row.id} rows={orders} />;
}

export function TradeTable({ trades }: { trades: Trade[] }) {
  const columns: Column<Trade>[] = [
    { key: "id", header: "ID", render: (row) => row.id },
    { key: "symbol", header: "Symbol", render: (row) => row.symbol },
    { key: "side", header: "Side", render: (row) => row.side.toUpperCase() },
    { key: "quantity", header: "Qty", align: "right", render: (row) => formatQuantity(row.quantity) },
    { key: "price", header: "Price", align: "right", render: (row) => <MoneyText value={row.price} /> },
    { key: "amount", header: "Amount", align: "right", render: (row) => <MoneyText value={row.amount} /> },
    { key: "fees", header: "Fees", align: "right", render: (row) => <MoneyText value={row.fees} /> },
    { key: "date", header: "Date", render: (row) => formatDate(row.trade_date) },
    { key: "comment", header: "Comment", render: (row) => row.comment || "-" }
  ];
  return <DataTable columns={columns} emptyTitle="No trades" getRowKey={(row) => row.id} rows={trades} />;
}

export function CashLedgerTable({ density, entries }: { density?: "default" | "compact"; entries: CashLedgerEntry[] }) {
  const columns: Column<CashLedgerEntry>[] = [
    { key: "id", header: "ID", render: (row) => row.id },
    { key: "event", header: "Event", render: (row) => row.event_type },
    { key: "amount", header: "Amount", align: "right", render: (row) => <MoneyText value={row.amount} /> },
    { key: "note", header: "Note", render: (row) => row.note ?? "-" }
  ];
  return <DataTable columns={columns} density={density} emptyTitle="No cash ledger entries" getRowKey={(row) => row.id} rows={entries} />;
}
