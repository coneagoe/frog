import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { listAccounts, listPositions, listOrders, listTrades, listCashLedger } from "@/lib/api-client";
import { TradePage } from "./trade-page";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams()
}));

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => ({ remove: vi.fn() }))
}));

vi.mock("@/lib/api-client", () => ({
  listAccounts: vi.fn().mockResolvedValue([
    { id: 1, name: "demo", initial_cash: "100000.00", status: "active", base_currency: "CNY" }
  ]),
  listPositions: vi.fn().mockResolvedValue([]),
  listOrders: vi.fn().mockResolvedValue([]),
  listTrades: vi.fn().mockResolvedValue([]),
  listCashLedger: vi.fn().mockResolvedValue([]),
  cancelOrder: vi.fn()
}));

describe("TradePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the simplified trade workspace", async () => {
    render(<TradePage />);

    // Wait for async account loading and assert core text appears
    expect(await screen.findByText(/Submit paper orders/)).toBeInTheDocument();

    // Core trading UI elements are present
    expect(screen.getByText("Chart symbol")).toBeInTheDocument();
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
});
