import { render, screen } from "@testing-library/react";
import { createChart } from "lightweight-charts";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getAnalytics, listAccounts, listSnapshots } from "@/lib/api-client";
import { AnalyticsPage } from "./analytics-page";

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => ({ addSeries: vi.fn(() => ({ setData: vi.fn() })), remove: vi.fn() })),
  LineSeries: vi.fn()
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams()
}));

vi.mock("@/lib/api-client", () => ({
  getAnalytics: vi.fn(),
  listAccounts: vi.fn(),
  listSnapshots: vi.fn()
}));

const getAnalyticsMock = vi.mocked(getAnalytics);
const listAccountsMock = vi.mocked(listAccounts);
const listSnapshotsMock = vi.mocked(listSnapshots);
const createChartMock = vi.mocked(createChart);

const analyticsPayload = {
  overview: {
    total_assets: "106000.0000",
    cash_available: "90000.0000",
    market_value: "15000.0000",
    realized_pnl: "6000.0000",
    unrealized_pnl: "500.0000",
    net_asset_value: "1.050000",
    share_count: "1000",
    total_return: { value: "0.060000", reason: null },
    simple_asset_return: { value: "0.050000", reason: null }
  },
  activity_daily: [{ period: "2026-06-16", order_count: 3, trade_count: 2, filled_count: 2, rejected_count: 1 }],
  activity_weekly: [{ period: "2026-W25", order_count: 3, trade_count: 2, filled_count: 2, rejected_count: 1 }],
  activity_monthly: [{ period: "2026-06", order_count: 3, trade_count: 2, filled_count: 2, rejected_count: 1 }],
  execution: {
    order_count: 3,
    filled_count: 2,
    rejected_count: 1,
    fill_rate: { value: "0.666667", reason: null },
    rejection_rate: { value: "0.333333", reason: null },
    reject_reasons: [{ reason: "INSUFFICIENT_CASH", count: 1 }]
  },
  trade_quality: {
    closed_count: 1,
    win_rate: { value: "1.000000", reason: null },
    avg_win: { value: "89.0000", reason: null },
    avg_loss: { value: null, reason: "no_losses" },
    payoff_ratio: { value: null, reason: "no_losses" },
    profit_factor: { value: null, reason: "no_losses" },
    consecutive_wins: 1,
    consecutive_losses: 0,
    avg_holding_days: { value: "4", reason: null },
    round_trips: [
      {
        id: 1,
        symbol: "000001.SZ",
        open_trade_date: "2026-06-16",
        close_trade_date: "2026-06-20",
        entry_amount: "1000.0000",
        exit_amount: "1100.0000",
        fees: "11.0000",
        realized_pnl: "89.0000",
        return_pct: "0.089000",
        holding_days: 4,
        status: "closed"
      }
    ]
  },
  risk: {
    max_drawdown: { value: "-0.100000", reason: null },
    current_drawdown: { value: "-0.050000", reason: null },
    sharpe: { value: null, reason: "insufficient_data" },
    sortino: { value: null, reason: "insufficient_data" },
    calmar: { value: null, reason: "insufficient_data" }
  }
};

describe("AnalyticsPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    createChartMock.mockReturnValue({ addSeries: vi.fn(() => ({ setData: vi.fn() })), remove: vi.fn() } as never);
    listAccountsMock.mockResolvedValue([{ id: 1, name: "demo", initial_cash: "100000.00", status: "active", base_currency: "CNY" }]);
    listSnapshotsMock.mockResolvedValue([]);
    getAnalyticsMock.mockResolvedValue(analyticsPayload);
  });

  it("renders the analytics dashboard sections", async () => {
    render(<AnalyticsPage />);

    expect(await screen.findByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Activity")).toBeInTheDocument();
    expect(screen.getByText("Execution")).toBeInTheDocument();
    expect(screen.getByText("Trade Quality")).toBeInTheDocument();
    expect(screen.getByText("Risk & Drawdown")).toBeInTheDocument();
    expect(screen.getByText("Insufficient Cash")).toBeInTheDocument();
    expect(screen.getByText("000001.SZ")).toBeInTheDocument();
  });

  it("renders NAV analytics fields", async () => {
    render(<AnalyticsPage />);

    expect(await screen.findByText("NAV Return")).toBeInTheDocument();
    expect(screen.getByText("Unit NAV")).toBeInTheDocument();
    expect(screen.getByText("Share Count")).toBeInTheDocument();
    expect(screen.getByText("1.050000")).toBeInTheDocument();
  });

  it("shows insufficient data reasons for unavailable metrics", async () => {
    getAnalyticsMock.mockResolvedValueOnce(undefined as never);
    render(<AnalyticsPage />);

    const submittedOrdersCard = await screen.findByText("Submitted Orders");
    const closedRoundTripsCard = screen.getByText("Closed Round Trips");

    expect(submittedOrdersCard.closest(".metric-card")).toHaveTextContent("-");
    expect(submittedOrdersCard.closest(".metric-card")).not.toHaveTextContent("0");
    expect(closedRoundTripsCard.closest(".metric-card")).toHaveTextContent("-");
    expect(closedRoundTripsCard.closest(".metric-card")).not.toHaveTextContent("0");
  });
});
