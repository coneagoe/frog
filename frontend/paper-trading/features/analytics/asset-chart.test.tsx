import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AnalyticsEvent, SnapshotAnalyticsEvent } from "@/lib/types";
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

const initialPoint = {
  event_type: "snapshot",
  id: 1,
  point_type: "initial",
  event_at: "2026-09-10T09:30:00Z",
  quality: "valid",
  timezone: "UTC",
  quality_status: "valid",
  invalid_reason: null,
  nav: "1",
  shares: "100000",
  share: "100000"
} satisfies SnapshotAnalyticsEvent;

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
    const invalidPoint = {
      ...initialPoint,
      id: 2,
      event_at: "2026-09-10T11:00:00Z",
      quality: "invalid",
      invalid_reason: "missing_nav",
      nav: null,
      shares: null,
      share: null
    } satisfies SnapshotAnalyticsEvent;
    const tradingPoint = {
      ...initialPoint,
      id: 3,
      point_type: "trading",
      event_at: "2026-09-10T15:00:00Z",
      nav: "1.1",
      shares: "100000",
      share: "100000"
    } satisfies SnapshotAnalyticsEvent;
    const malformedTimestampPoint = {
      ...initialPoint,
      id: 4,
      event_at: "not-a-timestamp",
      nav: "1.2",
      share: "100000"
    } satisfies SnapshotAnalyticsEvent;

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
        quality: "valid",
        timezone: "UTC",
        quality_status: "valid",
        invalid_reason: null,
        nav: "1",
        shares: "100000",
        share: "100000"
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
        event_type: "withdrawal",
        id: 5,
        occurred_at: "2026-09-10T12:00:00Z",
        amount: "1000",
        effective_nav: "1",
        share_delta: "-1000"
      },
      {
        event_type: "corporate_action",
        id: 6,
        event_at: "2026-09-10T13:00:00Z",
        symbol: "000001.SZ",
        action_type: "dividend",
        parameters: { per_share_amount: "1" },
        impact: {} as never,
        created_at: "2026-09-10T13:00:00Z"
      },
      {
        event_type: "snapshot",
        id: 3,
        event_at: "2026-09-10T11:00:00Z",
        point_type: "trading",
        quality: "invalid",
        timezone: "UTC",
        quality_status: "invalid",
        invalid_reason: "missing_nav",
        nav: null,
        shares: null,
        share: null
      },
      {
        event_type: "snapshot",
        id: 4,
        event_at: "2026-09-10T15:00:00Z",
        point_type: "trading",
        quality: "valid",
        timezone: "UTC",
        quality_status: "valid",
        invalid_reason: null,
        nav: "1.1",
        shares: "150000",
        share: "150000"
      }
    ] satisfies AnalyticsEvent[];

    render(<AssetChart events={eventSeries} />);

    expect(setDataMock).toHaveBeenCalledWith([
      { time: toChartTime("2026-09-10T09:30:00Z"), value: 1 },
      { time: toChartTime("2026-09-10T15:00:00Z"), value: 1.1 }
    ]);
  });

  it("renders the existing empty state when no valid NAV points exist", () => {
    render(<AssetChart events={[{ ...initialPoint, nav: null }]} />);

    expect(screen.getByText("No valid NAV points")).toBeInTheDocument();
    expect(createChartMock).not.toHaveBeenCalled();
  });

  it("renders same-second valid NAV points in server order", () => {
    const sameSecondPoint = {
      ...initialPoint,
      id: 2,
      point_type: "trading",
      nav: "1.1",
      share: "100000"
    } satisfies SnapshotAnalyticsEvent;

    render(<AssetChart events={[initialPoint, sameSecondPoint]} />);

    expect(setDataMock).toHaveBeenCalledWith([
      { time: toChartTime(initialPoint.event_at), value: 1 },
      { time: toChartTime(initialPoint.event_at) + 1, value: 1.1 }
    ]);
  });
});
