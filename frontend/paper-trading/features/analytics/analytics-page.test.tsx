import { render, screen } from "@testing-library/react";
import { createChart } from "lightweight-charts";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { listAccounts, listCashLedger, listSnapshots, listTrades } from "@/lib/api-client";
import { AnalyticsPage } from "./analytics-page";

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => ({ addSeries: vi.fn(() => ({ setData: vi.fn() })), remove: vi.fn() })),
  LineSeries: vi.fn()
}));

vi.mock("@/lib/api-client", () => ({
  listAccounts: vi.fn(),
  listCashLedger: vi.fn(),
  listSnapshots: vi.fn(),
  listTrades: vi.fn()
}));

const listAccountsMock = vi.mocked(listAccounts);
const listSnapshotsMock = vi.mocked(listSnapshots);
const listTradesMock = vi.mocked(listTrades);
const listCashLedgerMock = vi.mocked(listCashLedger);
const createChartMock = vi.mocked(createChart);

describe("AnalyticsPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    createChartMock.mockReturnValue({ addSeries: vi.fn(() => ({ setData: vi.fn() })), remove: vi.fn() } as never);
    listAccountsMock.mockResolvedValue([{ id: 1, name: "demo", initial_cash: "100000.00", status: "active", base_currency: "CNY" }]);
    listTradesMock.mockResolvedValue([]);
    listCashLedgerMock.mockResolvedValue([]);
  });

  it("renders latest total assets and realized pnl", async () => {
    listSnapshotsMock.mockResolvedValue([
      {
        id: 1,
        account_id: 1,
        trade_date: "2026-06-16",
        cash_available: "90000.00",
        cash_frozen: "1000.00",
        market_value: "15000.00",
        total_assets: "106000.00",
        realized_pnl: "6000.00",
        unrealized_pnl: "500.00",
        position_count: 2,
        order_count: 3,
        trade_count: 4
      }
    ]);

    render(<AnalyticsPage />);

    expect((await screen.findAllByText("¥106,000.00")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("¥6,000.00").length).toBeGreaterThan(0);
  });

  it("shows an empty snapshot state", async () => {
    listSnapshotsMock.mockResolvedValue([]);

    render(<AnalyticsPage />);

    expect((await screen.findAllByText("No snapshots yet")).length).toBeGreaterThan(0);
  });
});
