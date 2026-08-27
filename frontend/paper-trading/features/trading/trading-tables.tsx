import { DataTable, type Column } from "@/components/data-table";
import { MoneyText } from "@/components/money-text";
import { StatusBadge } from "@/components/status-badge";
import { formatDate, formatQuantity } from "@/lib/format";
import type { CashLedgerEntry, Order, Position, Trade } from "@/lib/types";

function StockNameCell({ name, compact }: { name: string | null; compact?: boolean }) {
  const stockName = name || "-";
  return <span className={compact ? "stock-name stock-name--compact" : "stock-name"} title={name || undefined}>{stockName}</span>;
}

function positionReturnPercent(position: Position): number | null {
  if (position.unrealized_pnl === null) {
    return null;
  }

  const cost = Number(position.cost_amount);
  const unrealizedPnl = Number(position.unrealized_pnl);
  if (!Number.isFinite(cost) || cost === 0 || !Number.isFinite(unrealizedPnl)) {
    return null;
  }

  const returnPercent = (unrealizedPnl / cost) * 100;
  if (!Number.isFinite(returnPercent)) {
    return null;
  }

  return returnPercent;
}

function positionWeightPercent(
  position: Position,
  accountNav: string | null | undefined,
  accountShareCount: string | null | undefined
): number | null {
  const nav = Number(accountNav);
  const shareCount = Number(accountShareCount);
  const quantity = Number(position.total_quantity);
  const markPrice = Number(position.mark_price);

  if (
    accountNav === null ||
    accountNav === undefined ||
    accountShareCount === null ||
    accountShareCount === undefined ||
    position.mark_price === null ||
    !Number.isFinite(nav) ||
    nav <= 0 ||
    !Number.isFinite(shareCount) ||
    shareCount <= 0 ||
    !Number.isFinite(quantity) ||
    quantity <= 0 ||
    !Number.isFinite(markPrice) ||
    markPrice < 0
  ) {
    return null;
  }

  const weightPercent = (quantity * markPrice / (nav * shareCount)) * 100;
  return Number.isFinite(weightPercent) ? weightPercent : null;
}

function positionReturn(position: Position): { value: string; className: "positive" | "negative" | "default" } | null {
  const returnPercent = positionReturnPercent(position);
  if (returnPercent === null) {
    return null;
  }

  return {
    value: `${returnPercent > 0 ? "+" : ""}${returnPercent.toFixed(2)}%`,
    className: returnPercent > 0 ? "positive" : returnPercent < 0 ? "negative" : "default"
  };
}

export function PositionTable({
  accountNav,
  accountShareCount,
  density,
  positions
}: {
  accountNav?: string | null;
  accountShareCount?: string | null;
  density?: "default" | "compact";
  positions: Position[];
}) {
  const columns: Column<Position>[] = [
    { key: "symbol", header: "Symbol", render: (row) => row.symbol, sortable: (row) => row.symbol },
    { key: "stock", header: "Stock", render: (row) => <StockNameCell compact={density === "compact"} name={row.stock_name} />, sortable: (row) => row.stock_name },
    { key: "total", header: "Total", align: "right", render: (row) => formatQuantity(row.total_quantity), sortable: (row) => row.total_quantity },
    { key: "frozen", header: "Frozen", align: "right", render: (row) => formatQuantity(row.frozen_quantity), sortable: (row) => row.frozen_quantity },
    ...(accountNav !== undefined && accountShareCount !== undefined
      ? [{
          key: "weight",
          header: "Weight",
          align: "right" as const,
          render: (row: Position) => {
            const weightPercent = positionWeightPercent(row, accountNav, accountShareCount);
            return weightPercent === null ? <span className="muted">—</span> : `${weightPercent.toFixed(2)}%`;
          },
          sortable: (row: Position) => positionWeightPercent(row, accountNav, accountShareCount)
        }]
      : []),
    {
      key: "return",
      header: "Return",
      align: "right",
      render: (row) => {
        const result = positionReturn(row);
        return result ? <span className={result.className}>{result.value}</span> : <span className="muted">—</span>;
      },
      sortable: positionReturnPercent
    }
  ];
  return <DataTable columns={columns} density={density} emptyTitle="No positions" getRowKey={(row) => row.symbol} resetKey={positions} rows={positions} />;
}

export function OrderTable({
  orders,
  onCancel,
  onDelete,
  deletingOrderId,
  editingOrderId,
  editingValue,
  onEditStart,
  onEditValueChange,
  onEditSave,
  onEditCancel
}: {
  orders: Order[];
  onCancel: (orderId: number) => void;
  onDelete?: (orderId: number) => void;
  deletingOrderId?: number | null;
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
    { key: "stock", header: "Stock", render: (row) => <StockNameCell name={row.stock_name} /> },
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
            <div className="actions">
              <button className="button" onClick={() => onEditSave?.(row.id)} type="button">Save</button>
              <button className="button button--secondary" onClick={() => onEditCancel?.()} type="button">Cancel</button>
            </div>
          );
        }
        return (
          <div className="actions">
            {cancellable.has(row.status)
              ? <button className="button button--secondary" onClick={() => onCancel(row.id)} type="button">Cancel</button>
              : null}
            {canEdit ? <button className="button button--secondary" onClick={() => onEditStart?.(row.id)} type="button">Edit</button> : null}
            {onDelete ? (
              <button
                className="button button--secondary"
                disabled={deletingOrderId === row.id}
                onClick={() => onDelete(row.id)}
                type="button"
              >
                {deletingOrderId === row.id ? "Deleting..." : "Delete"}
              </button>
            ) : null}
          </div>
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
    { key: "stock", header: "Stock", render: (row) => <StockNameCell name={row.stock_name} /> },
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

const cashEventLabels: Record<string, string> = {
  deposit: "Deposit",
  withdrawal: "Withdrawal",
  freeze: "Freeze",
  release: "Release",
  trade: "Trade",
  fee: "Fee",
  corporate_action: "Corporate action"
};

export function CashLedgerTable({ density, entries }: { density?: "default" | "compact"; entries: CashLedgerEntry[] }) {
  const columns: Column<CashLedgerEntry>[] = [
    { key: "event", header: "Event", render: (row) => cashEventLabels[row.event_type] ?? row.event_type },
    { key: "date", header: "Date", render: (row) => row.trade_date ? formatDate(row.trade_date) : "-" },
    { key: "amount", header: "Amount", align: "right", render: (row) => <MoneyText value={row.amount} /> },
    { key: "nav", header: "NAV", align: "right", render: (row) => row.net_asset_value ?? "-" },
    { key: "shares", header: "Share Delta", align: "right", render: (row) => row.share_delta ?? "-" },
    { key: "residual", header: "Rounding residual", align: "right", render: (row) => <MoneyText value={row.rounding_residual} /> },
    { key: "note", header: "Note", render: (row) => row.note ?? "-" }
  ];
  return <DataTable columns={columns} density={density} emptyTitle="No cash ledger entries" getRowKey={(row) => row.id} rows={entries} />;
}
