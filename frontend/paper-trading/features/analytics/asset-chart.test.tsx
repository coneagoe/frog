import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AnalyticsEvent, Snapshot } from "@/lib/types";
import { AssetChart } from "./asset-chart";

const { addSeriesMock, createChartMock, removeMock, setDataMock } = vi.hoisted(() => ({
  addSeriesMock: vi.fn(),
  createChartMock: vi.fn(),
  removeMock: vi.fn(),
  setDataMock: vi.fn()
}));

vi.mock("lightweight-charts", () => ({
  LineSeries: {},
  createChart: createChartMock
}));

const initialPoint: Snapshot = {
  id: 1,
  account_id: 1,
  trade_date: "2026-09-10",
  point_type: "initial",
  event_at: "2026-09-10T09:30:00Z",
  quality_status: "valid",
  invalid_reason: null,
  cash_available: "100000",
  cash_frozen: "0",
  market_value: "0",
  total_assets: "100000",
  realized_pnl: "0",
  unrealized_pnl: "0",
  net_asset_value: "1",
  share_count: "100000",
  cumulative_deposit: "100000",
  cumulative_withdrawal: "0",
  net_cash_flow: "100000",
  pending_settlement: "0",
  position_count: 0,
  order_count: 0,
  trade_count: 0
};

function toChartTime(eventAt: string) {
  return Math.floor(new Date(eventAt).getTime() / 1000);
}

describe("AssetChart", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    addSeriesMock.mockReturnValue({ setData: setDataMock });
    createChartMock.mockReturnValue({ addSeries: addSeriesMock, remove: removeMock });
  });

  it("renders only valid NAV values in server order", () => {
    const invalidPoint: Snapshot = {
      ...initialPoint,
      id: 2,
      event_at: "2026-09-10T11:00:00Z",
      quality_status: "invalid",
      invalid_reason: "missing_nav",
      net_asset_value: null,
      total_assets: "120000"
    };
    const tradingPoint: Snapshot = {
      ...initialPoint,
      id: 3,
      point_type: "trading",
      event_at: "2026-09-10T15:00:00Z",
      net_asset_value: "1.1"
    };
    const malformedTimestampPoint: Snapshot = {
      ...initialPoint,
      id: 4,
      event_at: "not-a-timestamp",
      net_asset_value: "1.2"
    };

    render(<AssetChart events={[initialPoint, invalidPoint, malformedTimestampPoint, tradingPoint]} />);

    expect(setDataMock).toHaveBeenCalledWith([
      { time: toChartTime(initialPoint.event_at), value: 1 },
      { time: toChartTime(tradingPoint.event_at), value: 1.1 }
    ]);
  });

  it("plots only valid snapshot NAV events from the analytics event series", () => {
    const eventSeries = [
      {
        event_type: "snapshot",
        id: 1,
        event_at: "2026-09-10T09:30:00Z",
        point_type: "initial",
        quality_status: "valid",
        invalid_reason: null,
        nav: "1",
        shares: "100000"
      },
      {
        event_type: "deposit",
        id: 2,
        occurred_at: "2026-09-10T10:00:00Z",
        amount: "50000",
        effective_nav: "1",
        share_delta: "50000"
      },
      {
        event_type: "snapshot",
        id: 3,
        event_at: "2026-09-10T11:00:00Z",
        point_type: "trading",
        quality_status: "invalid",
        invalid_reason: "missing_nav",
        nav: null,
        shares: null
      },
      {
        event_type: "snapshot",
        id: 4,
        event_at: "2026-09-10T15:00:00Z",
        point_type: "trading",
        quality_status: "valid",
        invalid_reason: null,
        nav: "1.1",
        shares: "150000"
      }
    ];

    render(<AssetChart events={eventSeries as AnalyticsEvent[]} />);

    expect(setDataMock).toHaveBeenCalledWith([
      { time: toChartTime("2026-09-10T09:30:00Z"), value: 1 },
      { time: toChartTime("2026-09-10T15:00:00Z"), value: 1.1 }
    ]);
  });

  it("renders the existing empty state when no valid NAV points exist", () => {
    render(<AssetChart events={[{ ...initialPoint, net_asset_value: null, total_assets: "100000" }]} />);

    expect(screen.getByText("No snapshots yet")).toBeInTheDocument();
    expect(createChartMock).not.toHaveBeenCalled();
  });

  it("renders same-second valid NAV points in server order", () => {
    const sameSecondPoint: Snapshot = {
      ...initialPoint,
      id: 2,
      point_type: "trading",
      net_asset_value: "1.1"
    };

    render(<AssetChart events={[initialPoint, sameSecondPoint]} />);

    expect(setDataMock).toHaveBeenCalledWith([
      { time: toChartTime(initialPoint.event_at), value: 1 },
      { time: toChartTime(initialPoint.event_at) + 1, value: 1.1 }
    ]);
  });
});
