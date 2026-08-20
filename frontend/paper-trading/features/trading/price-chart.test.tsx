import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LineSeries } from "lightweight-charts";
import { PriceChart } from "./price-chart";

const { createChartMock, addSeriesMock, removeMock, lineSeries } = vi.hoisted(() => ({
  createChartMock: vi.fn(),
  addSeriesMock: vi.fn(),
  removeMock: vi.fn(),
  lineSeries: {}
}));

vi.mock("lightweight-charts", () => ({
  LineSeries: lineSeries,
  createChart: createChartMock
}));

describe("PriceChart", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createChartMock.mockReturnValue({ addSeries: addSeriesMock, remove: removeMock });
  });

  it("creates a v5 line series for the selected symbol and cleans up", () => {
    const { unmount } = render(<PriceChart symbol="600519.SH" />);

    expect(screen.getByText("600519.SH Daily Chart")).toBeInTheDocument();
    expect(addSeriesMock).toHaveBeenCalledWith(LineSeries, { color: "#1d4ed8", lineWidth: 2 });

    unmount();
    expect(removeMock).toHaveBeenCalledOnce();
  });
});
