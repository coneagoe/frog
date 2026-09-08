import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMonitorTarget, deleteMonitorTarget, getMonitorTargetHealth, listMonitorTargets, setMonitorTargetEnabled, updateMonitorTarget } from "@/lib/api-client";
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

  it("keeps a Chinese alert-only notice visible on the monitor page", async () => {
    vi.mocked(listMonitorTargets).mockResolvedValue([]);
    render(<MonitorPage />);

    expect(await screen.findByText("本页面仅用于价格与指标预警，不会执行任何交易。")) .toBeInTheDocument();
  });
  it("filters by all four supported fields and has no workflow controls", async () => {
    vi.mocked(listMonitorTargets).mockResolvedValue([]);
    render(<MonitorPage />);
    await screen.findByText("No manual monitor targets yet");
    const healthCallsBeforeFilters = vi.mocked(getMonitorTargetHealth).mock.calls.length;
    await userEvent.selectOptions(screen.getByLabelText("Market filter"), "A");
    await userEvent.selectOptions(screen.getByLabelText("Frequency filter"), "daily");
    await userEvent.selectOptions(screen.getByLabelText("Status filter"), "true");
    await userEvent.selectOptions(screen.getByLabelText("Condition filter"), "rsi");
    expect(listMonitorTargets).toHaveBeenLastCalledWith({ market: "A", frequency: "daily", enabled: true, condition_type: "rsi" });
    expect(screen.getByText("morning-watch").closest(".monitor-health-panel")?.querySelectorAll("button, a")).toHaveLength(0);
    expect(getMonitorTargetHealth).toHaveBeenCalledTimes(healthCallsBeforeFilters);
  });

  it("shows a health error while preserving successful manual rows", async () => {
    vi.mocked(listMonitorTargets).mockResolvedValue([target]);
    vi.mocked(getMonitorTargetHealth).mockRejectedValue(new Error("Health service unavailable"));
    render(<MonitorPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Health service unavailable");
    expect(screen.getByText("000001")).toBeInTheDocument();
    expect(screen.queryByText("Health data is not available yet.")).not.toBeInTheDocument();
  });

  it("keeps health visible when manual loading fails", async () => {
    vi.mocked(listMonitorTargets).mockRejectedValue(new Error("Manual service unavailable"));
    render(<MonitorPage />);

    expect(await screen.findByText("workflow-only")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("Manual service unavailable");
  });

  it("suppresses stale health responses independently", async () => {
    let resolveFirst!: (value: typeof health) => void;
    vi.mocked(listMonitorTargets).mockResolvedValue([]);
    vi.mocked(getMonitorTargetHealth).mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; })).mockResolvedValueOnce({ ...health, targets: [{ ...health.targets[0], stock_code: "fresh-workflow" }] });
    render(<MonitorPage />);
    await userEvent.click(screen.getByRole("button", { name: "Refresh targets" }));
    expect(await screen.findByText("fresh-workflow")).toBeInTheDocument();
    resolveFirst(health);
    await waitFor(() => expect(screen.queryByText("workflow-only")).not.toBeInTheDocument());
  });

  it("updates health while retaining manual rows when a concurrent refresh has a manual failure", async () => {
    vi.mocked(listMonitorTargets).mockResolvedValueOnce([target]).mockRejectedValueOnce(new Error("Manual refresh unavailable"));
    vi.mocked(getMonitorTargetHealth).mockResolvedValueOnce(health).mockResolvedValueOnce({ ...health, targets: [{ ...health.targets[0], stock_code: "updated-workflow" }] });
    render(<MonitorPage />);
    await screen.findByText("000001");
    await userEvent.click(screen.getByRole("button", { name: "Refresh targets" }));

    expect(await screen.findByText("updated-workflow")).toBeInTheDocument();
    expect(screen.getByText("000001")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("Manual refresh unavailable");
  });

  it("updates manual targets while retaining health when a concurrent refresh has a health failure", async () => {
    const refreshedTarget = { ...target, stock_code: "000002" };
    vi.mocked(listMonitorTargets).mockResolvedValueOnce([target]).mockResolvedValueOnce([refreshedTarget]);
    vi.mocked(getMonitorTargetHealth).mockResolvedValueOnce(health).mockRejectedValueOnce(new Error("Health refresh unavailable"));
    render(<MonitorPage />);
    await screen.findByText("workflow-only");
    await userEvent.click(screen.getByRole("button", { name: "Refresh targets" }));

    expect(await screen.findByText("000002")).toBeInTheDocument();
    expect(screen.queryByText("000001")).not.toBeInTheDocument();
    expect(screen.getByText("workflow-only")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("Health refresh unavailable");
  });

  it("refreshes both resources after successful create and update", async () => {
    const createdTarget = { ...target, id: 18, stock_code: "000002" };
    const updatedTarget = { ...target, stock_code: "000003" };
    vi.mocked(listMonitorTargets).mockResolvedValueOnce([target]).mockResolvedValueOnce([createdTarget]).mockResolvedValueOnce([updatedTarget]);
    vi.mocked(createMonitorTarget).mockResolvedValue(target);
    vi.mocked(updateMonitorTarget).mockResolvedValue(target);
    vi.mocked(getMonitorTargetHealth).mockResolvedValueOnce(health).mockResolvedValueOnce({ ...health, targets: [{ ...health.targets[0], stock_code: "created-workflow" }] }).mockResolvedValueOnce({ ...health, targets: [{ ...health.targets[0], stock_code: "updated-workflow" }] });
    const user = userEvent.setup();
    render(<MonitorPage />);
    await screen.findByText("000001");

    await user.click(screen.getByRole("button", { name: "Create target" }));
    await user.type(screen.getByLabelText("Stock code"), "000002");
    await user.click(screen.getByRole("dialog", { name: "Create monitor target" }).querySelector('button[type="submit"]')!);
    await waitFor(() => expect(createMonitorTarget).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("000002")).toBeInTheDocument();
    expect(await screen.findByText("created-workflow")).toBeInTheDocument();
    expect(listMonitorTargets).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(getMonitorTargetHealth).toHaveBeenCalledTimes(2));

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.click(screen.getByRole("dialog", { name: "Edit monitor target" }).querySelector('button[type="submit"]')!);
    await waitFor(() => expect(updateMonitorTarget).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("000003")).toBeInTheDocument();
    expect(await screen.findByText("updated-workflow")).toBeInTheDocument();
    expect(listMonitorTargets).toHaveBeenCalledTimes(3);
    await waitFor(() => expect(getMonitorTargetHealth).toHaveBeenCalledTimes(3));
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

  it("refreshes both resources after a successful toggle", async () => {
    vi.mocked(listMonitorTargets).mockResolvedValue([target]);
    vi.mocked(setMonitorTargetEnabled).mockResolvedValue({ ...target, enabled: false });
    render(<MonitorPage />);
    await screen.findByText("000001");
    await userEvent.click(screen.getByRole("button", { name: "Disable 000001" }));

    await waitFor(() => expect(listMonitorTargets).toHaveBeenCalledTimes(2));
    expect(getMonitorTargetHealth).toHaveBeenCalledTimes(2);
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
    expect(getMonitorTargetHealth).toHaveBeenCalledTimes(2);
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
