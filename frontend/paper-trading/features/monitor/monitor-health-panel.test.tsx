import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { MonitorTargetHealthPage } from "@/lib/types";
import { MonitorHealthPanel } from "./monitor-health-panel";

const health: MonitorTargetHealthPage = { summary: { total: 75, running: 1, paused: 1, disabled: 0, triggered: 1, daily: 1, intraday: 1 }, items: [{ id: 1, stock_code: "000001", stock_name: "Ping An Bank", market: "A", frequency: "daily", workflow: null, enabled: true, paused: false, operational_state: "running", last_state: true, last_checked_at: "2026-09-07T09:30:00Z", triggered_at: "2026-09-07T09:30:00Z", latest_error: null }, { id: 2, stock_code: "00700", stock_name: null, market: "HK", frequency: "intraday", workflow: "morning-watch", enabled: true, paused: true, operational_state: "paused", last_state: false, last_checked_at: null, triggered_at: null, latest_error: null }], page: 1, page_size: 50, total_count: 75, total_pages: 2 };

describe("MonitorHealthPanel", () => {
  it("renders names, fallback and only read-only health controls", () => {
    render(<MonitorHealthPanel error={null} health={health} loading={false} onNextPage={vi.fn()} onPreviousPage={vi.fn()} />);

    expect(screen.getByText("Ping An Bank")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.getByText("Page 1 of 2 · 75 items")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Edit|Delete|Enable|Disable/ })).not.toBeInTheDocument();
  });

  it("disables its own pagination while loading and omits it for one page", () => {
    const { rerender } = render(<MonitorHealthPanel error={null} health={health} loading onNextPage={vi.fn()} onPreviousPage={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();

    rerender(<MonitorHealthPanel error={null} health={{ ...health, total_pages: 1 }} loading={false} onNextPage={vi.fn()} onPreviousPage={vi.fn()} />);
    expect(screen.queryByRole("navigation", { name: "Pagination" })).not.toBeInTheDocument();
  });
});
