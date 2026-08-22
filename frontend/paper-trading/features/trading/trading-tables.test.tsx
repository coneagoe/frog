import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { OrderTable, PositionTable, TradeTable } from "./trading-tables";

const position = {
  symbol: "000001.SZ",
  stock_name: "Ping An Bank",
  total_quantity: 100,
  frozen_quantity: 0,
  cost_amount: "1000.00",
  realized_pnl: "20.00",
  mark_price: "12.50",
  price_source: "real_time" as const,
  unrealized_pnl: "250.00"
};

const order = {
  id: 1,
  account_id: 1,
  symbol: "000001.SZ",
  stock_name: "Ping An Bank",
  side: "buy" as const,
  quantity: 100,
  limit_price: "10.00",
  trade_date: "2026-07-28",
  status: "accepted",
  filled_quantity: 0,
  frozen_cash: "1000.00",
  frozen_quantity: 100,
  rejection_code: null,
  rejection_reason: null,
  comment: null
};

const trade = {
  id: 1,
  order_id: 1,
  account_id: 1,
  symbol: "000001.SZ",
  stock_name: "Ping An Bank",
  side: "buy" as const,
  quantity: 100,
  price: "10.00",
  amount: "1000.00",
  fees: "5.00",
  trade_date: "2026-07-28",
  comment: null
};

function expectAdjacentStockHeader(table: HTMLElement) {
  const headers = within(table).getAllByRole("columnheader");
  const symbolIndex = headers.findIndex((header) => (header.textContent ?? "").startsWith("Symbol"));
  expect(headers[symbolIndex + 1]).toHaveTextContent("Stock");
}

describe("shared trading tables", () => {
  it.each([
    ["positions", () => <PositionTable positions={[position]} />],
    ["orders", () => <OrderTable orders={[order]} onCancel={() => undefined} />],
    ["trades", () => <TradeTable trades={[trade]} />]
  ])("renders an adjacent Stock column in %s", (_name, table) => {
    render(table());
    expectAdjacentStockHeader(screen.getByRole("table"));
    expect(screen.getByRole("cell", { name: "Ping An Bank" })).toBeInTheDocument();
  });

  it("falls back to a dash for a missing position name", () => {
    render(<PositionTable positions={[{ ...position, stock_name: null }]} />);
    expect(screen.getByRole("cell", { name: "-" })).toBeInTheDocument();
  });

  it("ellipsizes long names with a native title and compact modifier", () => {
    const name = "A very long stock name that should remain inspectable";
    render(<PositionTable density="compact" positions={[{ ...position, stock_name: name }]} />);
    const cell = screen.getByRole("cell", { name });
    const nameElement = within(cell).getByText(name);
    expect(nameElement).toHaveClass("stock-name", "stock-name--compact");
    expect(nameElement).toHaveAttribute("title", name);
  });

  it("labels the position PnL column Unrealized PnL", () => {
    render(<PositionTable positions={[position]} />);

    expect(screen.getByRole("columnheader", { name: "Unrealized PnL" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Realized PnL" })).not.toBeInTheDocument();
  });

  it("renders the API-supplied unrealized PnL value", () => {
    render(<PositionTable positions={[position]} />);

    expect(screen.getByRole("cell", { name: "¥250.00" })).toBeInTheDocument();
  });

  it("renders Unavailable when unrealized PnL is null", () => {
    render(<PositionTable positions={[{ ...position, unrealized_pnl: null }]} />);

    expect(screen.getAllByRole("cell", { name: "Unavailable" })).toHaveLength(2);
  });

  it("replaces Cost with 收益率 computed from unrealized PnL over cost", () => {
    render(<PositionTable positions={[position]} />);

    expect(screen.queryByRole("columnheader", { name: "Cost" })).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "收益率" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "25.00%" })).toBeInTheDocument();
  });

  it("renders Unavailable for 收益率 when cost or unrealized PnL cannot be used", () => {
    render(
      <PositionTable
        positions={[
          { ...position, symbol: "000002", cost_amount: "0.00", unrealized_pnl: "10.00" },
          { ...position, symbol: "000003", unrealized_pnl: null }
        ]}
      />
    );

    expect(screen.getAllByRole("cell", { name: "Unavailable" })).toHaveLength(3);
  });

  it("sorts positions when a column header is clicked", async () => {
    const user = userEvent.setup();
    render(
      <PositionTable
        positions={[
          { ...position, symbol: "000002", stock_name: "Beta", total_quantity: 50, cost_amount: "1000.00", unrealized_pnl: "100.00" },
          { ...position, symbol: "000001", stock_name: "Alpha", total_quantity: 200, cost_amount: "1000.00", unrealized_pnl: "250.00" }
        ]}
      />
    );

    expect(screen.getAllByRole("row").slice(1).map((row) => within(row).getAllByRole("cell")[0].textContent)).toEqual(["000002", "000001"]);

    await user.click(within(screen.getByRole("columnheader", { name: "Symbol" })).getByRole("button", { name: "Symbol" }));
    expect(screen.getAllByRole("row").slice(1).map((row) => within(row).getAllByRole("cell")[0].textContent)).toEqual(["000001", "000002"]);

    await user.click(within(screen.getByRole("columnheader", { name: "收益率" })).getByRole("button", { name: "收益率" }));
    expect(screen.getAllByRole("row").slice(1).map((row) => within(row).getAllByRole("cell")[0].textContent)).toEqual(["000002", "000001"]);
  });
});
