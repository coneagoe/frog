import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { deleteMonitorTarget, getMonitorTargetHealth, listMonitorTargets, setMonitorTargetEnabled } from "@/lib/api-client";
import { MonitorPage } from "./monitor-page";

vi.mock("@/lib/api-client", () => ({ listMonitorTargets: vi.fn(), getMonitorTargetHealth: vi.fn(), createMonitorTarget: vi.fn(), updateMonitorTarget: vi.fn(), setMonitorTargetEnabled: vi.fn(), deleteMonitorTarget: vi.fn() }));
const target = { id: 17, stock_code: "000001", market: "A" as const, frequency: "daily" as const, reset_mode: "auto" as const, enabled: true, last_state: false, triggered_at: null, created_at: null, note: "watch", condition: { type: "price_threshold" as const, direction: "above" as const, value: 10 } };
const health = { summary: { total: 1, running: 1, paused: 0, disabled: 0, triggered: 0, daily: 1, intraday: 0 }, targets: [{ id: 99, stock_code: "workflow-only", market: "A" as const, frequency: "daily" as const, workflow: "morning-watch", enabled: true, paused: false, operational_state: "running" as const, last_state: false, last_checked_at: null, triggered_at: null, latest_error: null }] };

describe("MonitorPage", () => {
  beforeEach(() => { vi.resetAllMocks(); vi.mocked(getMonitorTargetHealth).mockResolvedValue(health); });
  it("loads operational health above manual targets and refreshes both resources", async () => {
    vi.mocked(listMonitorTargets).mockResolvedValue([target]);
    render(<MonitorPage />);

    await screen.findByRole("heading", { name: "Operational health" });
    expect(listMonitorTargets).toHaveBeenCalledWith({});
    expect(getMonitorTargetHealth).toHaveBeenCalledTimes(1);
    expect(screen.getByText("morning-watch")).toBeInTheDocument();
    expect(screen.getByText("morning-watch").closest(".monitor-health-panel")?.querySelectorAll("button, a")).toHaveLength(0);

    await userEvent.click(screen.getByRole("button", { name: "Refresh targets" }));
    await waitFor(() => expect(getMonitorTargetHealth).toHaveBeenCalledTimes(2));
    expect(listMonitorTargets).toHaveBeenCalledTimes(2);
  });
  it("filters by all four supported fields and has no workflow controls", async () => {
    vi.mocked(listMonitorTargets).mockResolvedValue([]);
    render(<MonitorPage />);
    await screen.findByText("No manual monitor targets yet");
    await userEvent.selectOptions(screen.getByLabelText("Market filter"), "A");
    await userEvent.selectOptions(screen.getByLabelText("Frequency filter"), "daily");
    await userEvent.selectOptions(screen.getByLabelText("Status filter"), "true");
    await userEvent.selectOptions(screen.getByLabelText("Condition filter"), "rsi");
    expect(listMonitorTargets).toHaveBeenLastCalledWith({ market: "A", frequency: "daily", enabled: true, condition_type: "rsi" });
    expect(screen.getByText("morning-watch").closest(".monitor-health-panel")?.querySelectorAll("button, a")).toHaveLength(0);
  });

  it("refreshes after enable and keeps rows when a mutation fails", async () => {
    vi.mocked(listMonitorTargets).mockResolvedValue([target]);
    vi.mocked(setMonitorTargetEnabled).mockRejectedValue(new Error("Permission denied"));
    render(<MonitorPage />);
    await screen.findByText("000001");
    await userEvent.click(screen.getByRole("button", { name: "Disable 000001" }));
    expect(setMonitorTargetEnabled).toHaveBeenCalledWith(17, false);
    expect(await screen.findByRole("alert")).toHaveTextContent("Permission denied");
    expect(screen.getByText("000001")).toBeInTheDocument();
  });

  it("confirms permanent deletion before refreshing the list", async () => {
    vi.mocked(listMonitorTargets).mockResolvedValue([target]);
    vi.mocked(deleteMonitorTarget).mockResolvedValue(undefined);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<MonitorPage />);
    await screen.findByText("000001");
    await userEvent.click(screen.getByRole("button", { name: "Delete 000001" }));
    expect(confirm).toHaveBeenCalledWith("Permanently delete monitor target 000001?");
    expect(deleteMonitorTarget).toHaveBeenCalledWith(17);
    await waitFor(() => expect(listMonitorTargets).toHaveBeenCalledTimes(2));
  });

  it("keeps a later in-flight row action disabled when an earlier action completes", async () => {
    let resolveToggle!: () => void;
    let resolveDelete!: () => void;
    vi.mocked(listMonitorTargets).mockResolvedValue([target, { ...target, id: 18, stock_code: "000002" }]);
    vi.mocked(setMonitorTargetEnabled).mockImplementationOnce(() => new Promise((resolve) => { resolveToggle = resolve; }));
    vi.mocked(deleteMonitorTarget).mockImplementationOnce(() => new Promise((resolve) => { resolveDelete = resolve; }));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<MonitorPage />);
    await screen.findByText("000001");

    await userEvent.click(screen.getByRole("button", { name: "Disable 000001" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete 000002" }));
    expect(screen.getByRole("button", { name: "Delete 000002" })).toBeDisabled();

    resolveToggle();
    await waitFor(() => expect(listMonitorTargets).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("button", { name: "Delete 000002" })).toBeDisabled();

    resolveDelete();
    await waitFor(() => expect(listMonitorTargets).toHaveBeenCalledTimes(3));
    expect(screen.getByRole("button", { name: "Delete 000002" })).toBeEnabled();
  });

  it("suppresses stale list responses", async () => {
    let resolveFirst!: (items: typeof target[]) => void;
    vi.mocked(listMonitorTargets).mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; })).mockResolvedValueOnce([]);
    render(<MonitorPage />);
    await userEvent.click(screen.getByRole("button", { name: "Refresh targets" }));
    await screen.findByText("No manual monitor targets yet");
    resolveFirst([target]);
    await waitFor(() => expect(screen.queryByText("000001")).not.toBeInTheDocument());
  });
});
