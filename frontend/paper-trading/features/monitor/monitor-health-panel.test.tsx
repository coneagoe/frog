import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { MonitorTargetHealth } from "@/lib/types";
import { MonitorHealthPanel } from "./monitor-health-panel";

const health: MonitorTargetHealth = {
  summary: { total: 2, running: 1, paused: 1, disabled: 0, triggered: 1, daily: 1, intraday: 1 },
  targets: [
    { id: 1, stock_code: "000001", market: "A", frequency: "daily", workflow: null, enabled: true, paused: false, operational_state: "running", last_state: true, last_checked_at: "2026-09-07T09:30:00Z", triggered_at: "2026-09-07T09:30:00Z", latest_error: null },
    { id: 2, stock_code: "00700", market: "HK", frequency: "intraday", workflow: "morning-watch", enabled: true, paused: true, operational_state: "paused", last_state: false, last_checked_at: null, triggered_at: null, latest_error: { kind: "market_data", summary: "Quote unavailable", detail: "Provider timeout", occurred_at: "2026-09-07T09:31:00Z" } }
  ]
};

describe("MonitorHealthPanel", () => {
  it("renders the operational overview and read-only target health table", () => {
    const { container } = render(<MonitorHealthPanel health={health} loading={false} />);

    expect(screen.getByRole("heading", { name: "Operational health" })).toBeInTheDocument();
    for (const counter of ["Total", "Running", "Paused", "Disabled", "Triggered", "Daily", "Intraday"]) {
      expect(screen.getAllByText(counter).length).toBeGreaterThan(0);
    }
    expect(screen.getByText("Manual")).toBeInTheDocument();
    expect(screen.getByText("morning-watch")).toBeInTheDocument();
    expect(screen.getAllByText("Running")).toHaveLength(2);
    expect(screen.getAllByText("Paused")).toHaveLength(2);
    expect(screen.getAllByText("Triggered")).toHaveLength(2);
    expect(screen.getByText("Not triggered")).toBeInTheDocument();
    expect(screen.getByText("Quote unavailable — Provider timeout")).toBeInTheDocument();
    expect(screen.getAllByText("—")).toHaveLength(3);
    expect(container.querySelector('time[datetime="2026-09-07T09:30:00Z"]')).toBeInTheDocument();
    expect(container.querySelectorAll("time")).toHaveLength(2);
    expect(container.querySelectorAll("button, a")).toHaveLength(0);
  });
});
