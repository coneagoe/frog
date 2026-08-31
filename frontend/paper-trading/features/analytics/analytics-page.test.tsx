import { render, screen, waitFor, within } from "@testing-library/react";
import { createChart } from "lightweight-charts";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getAnalytics, listAccounts } from "@/lib/api-client";
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
  listAccounts: vi.fn()
}));

const getAnalyticsMock = vi.mocked(getAnalytics);
const listAccountsMock = vi.mocked(listAccounts);
const createChartMock = vi.mocked(createChart);

function closestSection(element: HTMLElement): HTMLElement {
  const section = element.closest("section");
  if (!section) {
    throw new Error("Expected element to be wrapped in a <section>");
  }
  return section;
}

const analyticsPayload = {
  available: true as const,
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
  activity: {
    coverage_start: "2026-08-28",
    coverage_end: "2026-09-10",
    daily: { total_orders: "0.285714", successful_orders: "0.142857", failed_orders: "0.071429" },
    weekly: { total_orders: "1.333333", successful_orders: "0.666667", failed_orders: "0.333333" },
    monthly: { total_orders: "2.000000", successful_orders: "1.000000", failed_orders: "0.500000" }
  },
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
  },
  valuation_gaps: [],
  event_series: [{
    event_type: "snapshot",
    id: 1,
    event_at: "2026-09-10T15:00:00Z",
    point_type: "trading",
    quality: "valid",
    timezone: "UTC",
    invalid_reason: null,
    nav: "1.250000",
    shares: "1000",
    share: "1000"
  }]
};

describe("AnalyticsPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    createChartMock.mockReturnValue({ addSeries: vi.fn(() => ({ setData: vi.fn() })), remove: vi.fn() } as never);
    listAccountsMock.mockResolvedValue([{ id: 1, name: "demo", initial_cash: "100000.00", status: "active", base_currency: "CNY" }]);
    getAnalyticsMock.mockResolvedValue(analyticsPayload);
  });

  it("renders the asset chart in Overview instead of Risk & Drawdown", async () => {
    render(<AnalyticsPage />);

    const overview = closestSection(screen.getByRole("heading", { level: 2, name: "Overview" }));
    const risk = closestSection(screen.getByRole("heading", { level: 2, name: "Risk & Drawdown" }));

    await waitFor(() => {
      expect(overview.querySelector(".chart-surface")).toBeInTheDocument();
    });
    expect(risk.querySelector(".chart-surface")).not.toBeInTheDocument();
  });

  it("uses available analytics event series for the asset chart", async () => {
    render(<AnalyticsPage />);

    await waitFor(() => {
      expect(createChartMock).toHaveBeenCalled();
    });
    const setData = vi.mocked(createChartMock).mock.results[0]?.value.addSeries.mock.results[0]?.value.setData;
    expect(setData).toHaveBeenCalledWith([{ time: 1789052400, value: 1.25 }]);
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

  it("renders activity coverage and average order summaries", async () => {
    render(<AnalyticsPage />);

    expect(await screen.findByText("Activity Coverage")).toBeInTheDocument();
    expect(screen.getByText("2026-08-28")).toBeInTheDocument();
    expect(screen.getByText("2026-09-10")).toBeInTheDocument();
    expect(screen.getByText("Daily")).toBeInTheDocument();
    expect(screen.getByText("Weekly")).toBeInTheDocument();
    expect(screen.getByText("Monthly")).toBeInTheDocument();
    expect(screen.getAllByText("Total Orders")).toHaveLength(3);
    expect(screen.getAllByText("Successful Orders")).toHaveLength(3);
    expect(screen.getAllByText("Failed Orders")).toHaveLength(3);
    expect(screen.queryByText("Period")).not.toBeInTheDocument();
    expect(screen.queryByText("Trades")).not.toBeInTheDocument();

    const expectedUnits = [
      { label: "Daily", total: "0.286", successful: "0.143", failed: "0.071" },
      { label: "Weekly", total: "1.333", successful: "0.667", failed: "0.333" },
      { label: "Monthly", total: "2", successful: "1", failed: "0.5" }
    ];

    for (const unit of expectedUnits) {
      const unitQueries = within(closestSection(screen.getByRole("heading", { level: 3, name: unit.label })));
      expect(unitQueries.getByText("Total Orders").closest(".metric-card")).toHaveTextContent(unit.total);
      expect(unitQueries.getByText("Successful Orders").closest(".metric-card")).toHaveTextContent(unit.successful);
      expect(unitQueries.getByText("Failed Orders").closest(".metric-card")).toHaveTextContent(unit.failed);
    }
  });

  it("renders activity headings with the expected levels", async () => {
    render(<AnalyticsPage />);

    expect(await screen.findByRole("heading", { level: 2, name: "Activity" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Activity Coverage" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Daily" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Weekly" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Monthly" })).toBeInTheDocument();
  });

  it("shows activity as unavailable when no activity summary is returned", async () => {
    getAnalyticsMock.mockResolvedValueOnce({ ...analyticsPayload, activity: null });
    render(<AnalyticsPage />);

    const activityHeading = await screen.findByRole("heading", { level: 2, name: "Activity" });
    const activity = within(closestSection(activityHeading));

    expect(activity.getByText("Activity unavailable")).toHaveClass("muted");
    expect(activity.queryAllByRole("heading", { level: 3 })).toHaveLength(0);
    expect(activity.queryByText("Activity Coverage")).not.toBeInTheDocument();
    expect(activity.queryByText("Daily")).not.toBeInTheDocument();
    expect(activity.queryByText("Weekly")).not.toBeInTheDocument();
    expect(activity.queryByText("Monthly")).not.toBeInTheDocument();
    expect(activity.queryByText("Total Orders")).not.toBeInTheDocument();
    expect(activity.queryByText("Successful Orders")).not.toBeInTheDocument();
    expect(activity.queryByText("Failed Orders")).not.toBeInTheDocument();
    expect(activity.queryByText("0")).not.toBeInTheDocument();
    expect(activity.queryByText("0.286")).not.toBeInTheDocument();
    expect(activity.queryByText("1.333")).not.toBeInTheDocument();
  });

  it("renders NAV analytics fields", async () => {
    render(<AnalyticsPage />);

    expect(await screen.findByText("NAV Return")).toBeInTheDocument();
    expect(screen.getByText("Unit NAV")).toBeInTheDocument();
    expect(screen.getByText("Share Count")).toBeInTheDocument();
    expect(screen.getByText("1.050000")).toBeInTheDocument();
  });

  it("shows repair required state without rendering performance panels or a snapshot fallback", async () => {
    getAnalyticsMock.mockResolvedValue({ available: false, reason: "legacy_ordering_uncertain", valuation_gaps: null });

    render(<AnalyticsPage />);

    expect(await screen.findByText("Performance analytics unavailable")).toBeInTheDocument();
    expect(screen.getByText(/legacy ordering uncertain/)).toBeInTheDocument();
    expect(screen.queryByText("NAV Return")).not.toBeInTheDocument();
    expect(screen.queryByText("Activity")).not.toBeInTheDocument();
    expect(screen.queryByText("Execution")).not.toBeInTheDocument();
    expect(screen.queryByText("Trade Quality")).not.toBeInTheDocument();
    expect(screen.queryByText("Risk & Drawdown")).not.toBeInTheDocument();
    expect(screen.getByRole("combobox")).toHaveValue("1");
    expect(screen.getByRole("heading", { level: 2, name: "Overview" })).toBeInTheDocument();
    expect(document.querySelector(".chart-surface")).not.toBeInTheDocument();
  });

  it("shows valuation gaps outside the performance chart", async () => {
    getAnalyticsMock.mockResolvedValue({
      available: false,
      reason: "valuation_gap",
      valuation_gaps: [{ trade_date: "2026-09-10", missing_symbols: ["000001.SZ"], details: [{ reason: "missing_bar" }], resolved: false }]
    });
    render(<AnalyticsPage />);

    expect(await screen.findByRole("heading", { level: 2, name: "Valuation Gaps" })).toBeInTheDocument();
    expect(screen.getByText("000001.SZ")).toBeInTheDocument();
    expect(screen.getByText("Reason: missing_bar")).toBeInTheDocument();
    expect(screen.getByText("Unresolved")).toBeInTheDocument();
    expect(document.querySelector(".chart-surface")).not.toBeInTheDocument();
  });

  it("shows persisted valuation gaps for repair-unavailable analytics", async () => {
    getAnalyticsMock.mockResolvedValue({
      available: false,
      reason: "legacy_ordering_uncertain",
      valuation_gaps: [{ trade_date: "2026-09-10", missing_symbols: ["000001.SZ"], details: [{ reason: "missing_bar" }], resolved: false }]
    });
    render(<AnalyticsPage />);

    expect(await screen.findByText("Performance analytics unavailable")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Valuation Gaps" })).toBeInTheDocument();
    expect(screen.getByText("000001.SZ")).toBeInTheDocument();
    expect(screen.getByText("Reason: missing_bar")).toBeInTheDocument();
    expect(document.querySelector(".chart-surface")).not.toBeInTheDocument();
  });

  it("shows valuation gaps for available analytics too", async () => {
    getAnalyticsMock.mockResolvedValueOnce({
      ...analyticsPayload,
      valuation_gaps: [{ trade_date: "2026-09-10", missing_symbols: ["000001.SZ"], details: [{ reason: "stale_bar" }], resolved: false }]
    });

    render(<AnalyticsPage />);

    expect(await screen.findByRole("heading", { level: 2, name: "Valuation Gaps" })).toBeInTheDocument();
    expect(screen.getByText("Reason: stale_bar")).toBeInTheDocument();
  });

  it("renders the corporate action audit with formatted values and labels", async () => {
    getAnalyticsMock.mockResolvedValueOnce({
      ...analyticsPayload,
      event_series: [{
        event_type: "corporate_action",
        id: 4,
        event_at: "2026-09-10T15:00:00Z",
        symbol: "000001.SZ",
        action_type: "rights_issue",
        parameters: { price: "12.50", quantity: "100" },
        impact: {
          cash_delta: "-12.50",
          quantity_delta: "-100",
          before_quantity: "200",
          after_quantity: "100",
          before_cost_amount: "¥2000",
          after_cost_amount: "¥2000",
          before_cash_available: "100000.00",
          after_cash_available: "99987.50",
          affected_start_date: null,
          affected_end_date: null
        },
        created_at: "2026-09-10T15:00:00Z"
      }]
    });

    render(<AnalyticsPage />);

    const audit = closestSection(await screen.findByRole("heading", { level: 2, name: "Corporate Action Audit" }));
    expect(within(audit).getByRole("cell", { name: /Rights Issue/ })).toBeInTheDocument();
    expect(within(audit).getByRole("cell", { name: /Price ¥12\.50\s*, Quantity 100/ })).toBeInTheDocument();
    expect(within(audit).getByText(/Qty 200 → 100/)).toBeInTheDocument();
    expect(within(audit).getByText(/¥100,000.00/)).toBeInTheDocument();
    expect(within(audit).getByText(/¥99,987.50/)).toBeInTheDocument();
  });
});
