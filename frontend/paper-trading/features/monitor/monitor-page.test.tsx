import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMonitorTarget, listMonitorTargets } from "@/lib/api-client";
import { MonitorPage } from "./monitor-page";

vi.mock("@/lib/api-client", () => ({
  listMonitorTargets: vi.fn(),
  createMonitorTarget: vi.fn(),
  updateMonitorTarget: vi.fn(),
  setMonitorTargetEnabled: vi.fn(),
  deleteMonitorTarget: vi.fn(),
}));

const target = {
  id: 17,
  stock_code: "000001",
  stock_name: "Ping An Bank",
  market: "A" as const,
  frequency: "daily" as const,
  reset_mode: "auto" as const,
  enabled: true,
  last_state: false,
  triggered_at: null,
  created_at: null,
  note: "watch",
  condition: { type: "price_threshold" as const, direction: "above" as const, value: 10 },
  target_type: "manual" as const,
  can_manage: true,
  paused: false,
  operational_state: "running" as const,
};
const page = (items = [target]) => ({
  items,
  summary: { total: 1, running: 1, paused: 0, disabled: 0, triggered: 0, daily: 1, intraday: 0 },
  pagination: { page: 1, page_size: 50, total_count: items.length, total_pages: 1 },
});

describe("MonitorPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(listMonitorTargets).mockResolvedValue(page());
  });

  it("starts read-only and only exposes management after explicit entry", async () => {
    const user = userEvent.setup();
    render(<MonitorPage />);

    await screen.findByText("000001");
    expect(screen.queryByRole("button", { name: /Edit 000001/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Enter management mode" }));

    expect(screen.getByRole("button", { name: /Edit 000001/ })).toBeInTheDocument();
  });

  it("uses one unified request and debounces filters", async () => {
    const user = userEvent.setup();
    render(<MonitorPage />);

    await screen.findByText("000001");
    expect(listMonitorTargets).toHaveBeenCalledWith({ page: 1, page_size: 50, sort: "default" });

    await user.selectOptions(screen.getByLabelText("Market filter"), "A");

    await waitFor(() => expect(listMonitorTargets).toHaveBeenLastCalledWith({ market: "A", page: 1, page_size: 50, sort: "default" }));
  });

  it("disables query controls while loading but keeps management mode available", async () => {
    render(<MonitorPage />);

    expect(screen.getByRole("button", { name: "Refresh targets" })).toBeDisabled();
    expect(screen.getByLabelText("Market filter")).toBeDisabled();
    expect(screen.getByLabelText("Frequency filter")).toBeDisabled();
    expect(screen.getByLabelText("Status filter")).toBeDisabled();
    expect(screen.getByLabelText("Condition type filter")).toBeDisabled();
    expect(screen.getByLabelText("Page size")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Clear filters" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Enter management mode" })).toBeEnabled();

    await screen.findByText("000001");
  });

  it("shows retryable errors without losing the previous response", async () => {
    vi.mocked(listMonitorTargets).mockRejectedValueOnce(new Error("Unavailable"));
    render(<MonitorPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Unavailable");
  });

  it("keeps create operation available in management mode", async () => {
    const user = userEvent.setup();
    render(<MonitorPage />);

    await screen.findByText("000001");
    await user.click(screen.getByRole("button", { name: "Enter management mode" }));
    await user.click(screen.getByRole("button", { name: "Create target" }));

    expect(screen.getByRole("dialog", { name: "Create monitor target" })).toBeInTheDocument();
    expect(createMonitorTarget).not.toHaveBeenCalled();
  });
});
