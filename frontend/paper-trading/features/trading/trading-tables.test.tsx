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
  const symbolIndex = headers.findIndex((header) => header.textContent === "Symbol");
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

  it("adds Weight before Return only when account scale is provided", () => {
    const { rerender } = render(<PositionTable positions={[position]} />);

    expect(screen.queryByRole("columnheader", { name: "Weight" })).not.toBeInTheDocument();

    rerender(<PositionTable accountNav="1.000000" accountShareCount="100000.000000" positions={[position]} />);
    expect(screen.getAllByRole("columnheader").map((header) => header.textContent)).toEqual([
      "Symbol",
      "Stock",
      "Total",
      "Frozen",
      "Weight",
      "Return"
    ]);
  });

  it("renders market value as a percentage of total account assets", () => {
    render(<PositionTable accountNav="1.000000" accountShareCount="100000.000000" positions={[position]} />);

    expect(screen.getByRole("cell", { name: "1.25%" })).toBeInTheDocument();
  });

  it.each([
    ["missing unit NAV", null, "100000.000000", position],
    ["zero unit NAV", "0", "100000.000000", position],
    ["non-finite unit NAV", "Infinity", "100000.000000", position],
    ["invalid share count", "1.000000", "not-a-number", position],
    ["zero quantity", "1.000000", "100000.000000", { ...position, total_quantity: 0 }],
    ["non-finite quantity", "1.000000", "100000.000000", { ...position, total_quantity: Number.NaN }],
    ["missing mark price", "1.000000", "100000.000000", { ...position, mark_price: null }]
  ])("renders a muted em dash for %s", (_name, accountNav, accountShareCount, invalidPosition) => {
    render(<PositionTable accountNav={accountNav} accountShareCount={accountShareCount} positions={[invalidPosition]} />);

    const weightCell = screen.getAllByRole("cell")[4];
    expect(within(weightCell).getByText("—")).toHaveClass("muted");
    expect(weightCell).not.toHaveTextContent("0.00%");
  });

  it("labels the position return column Return", () => {
    render(<PositionTable positions={[position]} />);

    expect(screen.getByRole("columnheader", { name: "Return" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Cost" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Unrealized PnL" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Realized PnL" })).not.toBeInTheDocument();
  });

  it("renders the calculated unrealized return value", () => {
    render(<PositionTable positions={[position]} />);

    expect(screen.getByRole("cell", { name: "+25.00%" })).toBeInTheDocument();
  });

  it("renders a muted em dash when unrealized PnL is null", () => {
    render(<PositionTable positions={[{ ...position, unrealized_pnl: null }]} />);

    const returnCell = screen.getByRole("cell", { name: "—" });
    expect(returnCell).toHaveClass("numeric");
    expect(within(returnCell).getByText("—")).toHaveClass("muted");
  });

  it.each([
    ["Symbol", ["000001.SZ", "000002.SZ"]],
    ["Stock", ["Alpha", "Zulu"]],
    ["Total", ["10", "20"]],
    ["Frozen", ["0", "5"]],
    ["Return", ["-10.00%", "+10.00%"]]
  ])("sorts %s ascending and descending", async (header, expected) => {
    const user = userEvent.setup();
    const rows = [
      { ...position, symbol: "000002.SZ", stock_name: "Zulu", total_quantity: 20, frozen_quantity: 5, cost_amount: "1000", unrealized_pnl: "100" },
      { ...position, symbol: "000001.SZ", stock_name: "Alpha", total_quantity: 10, frozen_quantity: 0, cost_amount: "1000", unrealized_pnl: "-100" }
    ];
    render(<PositionTable positions={rows} />);
    const table = screen.getByRole("table");
    const getValues = () => within(table).getAllByRole("row").slice(1).map((row) => within(row).getAllByRole("cell")[within(table).getAllByRole("columnheader").findIndex((column) => column.textContent?.startsWith(header))].textContent);

    await user.click(screen.getByRole("button", { name: header }));
    expect(getValues()).toEqual(expected);
    await user.click(screen.getByRole("button", { name: header }));
    expect(getValues()).toEqual([...expected].reverse());
  });

  it("keeps missing values last in both directions and does not mutate rows", async () => {
    const user = userEvent.setup();
    const rows = [
      { ...position, symbol: "B", stock_name: null, total_quantity: 2 },
      { ...position, symbol: "A", stock_name: "Alpha", total_quantity: 1 },
      { ...position, symbol: "C", stock_name: "", total_quantity: Number.NaN }
    ];
    const original = [...rows];
    render(<PositionTable positions={rows} />);
    const total = screen.getByRole("button", { name: "Total" });
    await user.click(total);
    expect(within(screen.getByRole("table")).getAllByRole("row").slice(1).map((row) => within(row).getAllByRole("cell")[2].textContent)).toEqual(["1", "2", "NaN"]);
    await user.click(total);
    expect(within(screen.getByRole("table")).getAllByRole("row").slice(1).map((row) => within(row).getAllByRole("cell")[0].textContent)).toEqual(["B", "A", "C"]);
    expect(rows).toEqual(original);
  });

  it("exposes one active sort state and supports keyboard sorting", async () => {
    const user = userEvent.setup();
    render(<PositionTable positions={[{ ...position, symbol: "B" }, { ...position, symbol: "A" }]} />);
    const table = screen.getByRole("table");
    const symbol = screen.getByRole("button", { name: "Symbol" });
    symbol.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("columnheader", { name: /Symbol/ })).toHaveAttribute("aria-sort", "ascending");
    expect(screen.getAllByRole("columnheader").filter((header) => header.hasAttribute("aria-sort"))).toHaveLength(1);
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("A");
    await user.click(screen.getByRole("button", { name: "Stock" }));
    expect(screen.getByRole("columnheader", { name: /Stock/ })).toHaveAttribute("aria-sort", "ascending");
    expect(screen.getByRole("columnheader", { name: /Symbol/ })).not.toHaveAttribute("aria-sort");
  });

  it("resets sorting when the positions array is replaced", async () => {
    const user = userEvent.setup();
    const first = [{ ...position, symbol: "B" }, { ...position, symbol: "A" }];
    const { rerender } = render(<PositionTable positions={first} />);
    await user.click(screen.getByRole("button", { name: "Symbol" }));
    const fresh = [{ ...position, symbol: "C" }, { ...position, symbol: "B" }];
    rerender(<PositionTable positions={fresh} />);
    expect(screen.getByRole("columnheader", { name: "Symbol" })).not.toHaveAttribute("aria-sort");
    expect(within(screen.getByRole("table")).getAllByRole("row")[1]).toHaveTextContent("C");
  });
});
