import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createOrder, listAccounts, listPositions, listOrders, listTrades, listCashLedger } from "@/lib/api-client";
import { TradePage } from "./trade-page";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams()
}));

vi.mock("lightweight-charts", () => ({
  LineSeries: {},
  createChart: vi.fn(() => ({ addSeries: vi.fn(), remove: vi.fn() }))
}));

vi.mock("@/lib/api-client", () => ({
  listAccounts: vi.fn().mockResolvedValue([
    { id: 1, name: "demo", initial_cash: "100000.00", status: "active", base_currency: "CNY" }
  ]),
  listPositions: vi.fn().mockResolvedValue([]),
  listOrders: vi.fn().mockResolvedValue([]),
  listTrades: vi.fn().mockResolvedValue([]),
  listCashLedger: vi.fn().mockResolvedValue([]),
  createOrder: vi.fn().mockResolvedValue({}),
  cancelOrder: vi.fn()
}));

describe("TradePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listAccounts.mockResolvedValue([
      { id: 1, name: "demo", initial_cash: "100000.00", status: "active", base_currency: "CNY" }
    ]);
  });

  it("renders the simplified trade workspace", async () => {
    render(<TradePage />);

    // Wait for async account loading and assert core text appears
    expect(await screen.findByText(/Submit paper orders/)).toBeInTheDocument();

    const chartSymbol = screen.getByLabelText("Chart symbol");
    const orderSymbol = screen.getByLabelText("Symbol");
    expect(chartSymbol.closest(".chart-workspace__toolbar")).toContainElement(chartSymbol);
    expect(chartSymbol.closest(".panel")).not.toBeInTheDocument();
    await userEvent.type(chartSymbol, "600519.SH");
    await userEvent.type(orderSymbol, "000001.SZ");
    expect(chartSymbol).toHaveValue("600519.SH");
    expect(orderSymbol).toHaveValue("000001.SZ");
    expect(screen.getByText("Limit Order")).toBeInTheDocument();

    // Account history and management sections are NOT rendered
    expect(screen.queryByText("Positions")).not.toBeInTheDocument();
    expect(screen.queryByText("Orders")).not.toBeInTheDocument();
    expect(screen.queryByText("Trades")).not.toBeInTheDocument();
    expect(screen.queryByText("Cash Ledger")).not.toBeInTheDocument();

    // Only listAccounts is called during initial load — no position/order/trade/ledger fetches
    expect(listAccounts).toHaveBeenCalled();
    expect(listPositions).not.toHaveBeenCalled();
    expect(listOrders).not.toHaveBeenCalled();
    expect(listTrades).not.toHaveBeenCalled();
    expect(listCashLedger).not.toHaveBeenCalled();
  });

  it("account selector is disabled when there are no accounts", async () => {
    listAccounts.mockResolvedValue([]);

    render(<TradePage />);

    expect(await screen.findByText(/No paper accounts yet/)).toBeInTheDocument();
  });

  it("submits the order-form symbol independently from the chart symbol", async () => {
    render(<TradePage />);

    expect(await screen.findByText(/Submit paper orders/)).toBeInTheDocument();
    const submitButton = screen.getByRole("button", { name: "Submit order" });
    await waitFor(() => expect(submitButton).toBeEnabled());
    await userEvent.type(screen.getByLabelText("Chart symbol"), "600519.SH");
    await userEvent.type(screen.getByLabelText("Symbol"), "000001.SZ");
    await userEvent.clear(screen.getByLabelText("Limit price"));
    await userEvent.type(screen.getByLabelText("Limit price"), "10.00");
    await userEvent.type(screen.getByLabelText("Trade date"), "2026-06-16");
    await userEvent.click(submitButton);

    expect(createOrder).toHaveBeenCalledWith(1, expect.objectContaining({ symbol: "000001.SZ" }));
    expect(createOrder).not.toHaveBeenCalledWith(1, expect.objectContaining({ symbol: "600519.SH" }));
  });
});
