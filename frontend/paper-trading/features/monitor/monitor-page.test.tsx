import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMonitorTarget, deleteMonitorTarget, getMonitorTargetHealth, listMonitorTargets, setMonitorTargetEnabled, updateMonitorTarget } from "@/lib/api-client";
import { MonitorPage } from "./monitor-page";

vi.mock("@/lib/api-client", () => ({ listMonitorTargets: vi.fn(), getMonitorTargetHealth: vi.fn(), createMonitorTarget: vi.fn(), updateMonitorTarget: vi.fn(), setMonitorTargetEnabled: vi.fn(), deleteMonitorTarget: vi.fn() }));

const target = { id: 17, stock_code: "000001", stock_name: "Ping An Bank", market: "A" as const, frequency: "daily" as const, reset_mode: "auto" as const, enabled: true, last_state: false, triggered_at: null, created_at: null, note: "watch", condition: { type: "price_threshold" as const, direction: "above" as const, value: 10 } };
const manualPage = (page = 1, totalPages = 2) => ({ items: [target], page, page_size: 50, total_count: 75, total_pages: totalPages });
const healthPage = (page = 1, totalPages = 2) => ({ summary: { total: 75, running: 1, paused: 0, disabled: 0, triggered: 0, daily: 1, intraday: 0 }, items: [{ id: 99, stock_code: "workflow-only", stock_name: null, market: "A" as const, frequency: "daily" as const, workflow: "morning-watch", enabled: true, paused: false, operational_state: "running" as const, last_state: false, last_checked_at: null, triggered_at: null, latest_error: null }], page, page_size: 50, total_count: 75, total_pages: totalPages });

describe("MonitorPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(listMonitorTargets).mockResolvedValue(manualPage());
    vi.mocked(getMonitorTargetHealth).mockResolvedValue(healthPage());
  });

  it("starts read-only and explicitly enters and exits management mode", async () => {
    const user = userEvent.setup();
    render(<MonitorPage />);
    await screen.findByText("000001");

    expect(screen.queryByRole("button", { name: "Create target" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Enter management mode" }));
    expect(screen.getByRole("button", { name: "Exit management mode" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create target" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Exit management mode" }));
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
  });

  it("shows a manual-target loading message before the first response", async () => {
    let resolveManual!: (value: ReturnType<typeof manualPage>) => void;
    let resolveHealth!: (value: ReturnType<typeof healthPage>) => void;
    vi.mocked(listMonitorTargets).mockImplementationOnce(() => new Promise((resolve) => { resolveManual = resolve; }));
    vi.mocked(getMonitorTargetHealth).mockImplementationOnce(() => new Promise((resolve) => { resolveHealth = resolve; }));
    render(<MonitorPage />);

    expect(screen.getByText("Loading manual targets…")).toBeInTheDocument();
    expect(screen.queryByText("No manual monitor targets yet")).not.toBeInTheDocument();

    await act(async () => {
      resolveManual(manualPage());
      resolveHealth(healthPage());
    });
  });

  it("closes an open editor when management mode exits", async () => {
    const user = userEvent.setup();
    render(<MonitorPage />);
    await screen.findByText("000001");

    await user.click(screen.getByRole("button", { name: "Enter management mode" }));
    await user.click(screen.getByRole("button", { name: "Create target" }));
    expect(screen.getByRole("dialog", { name: "Create monitor target" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Exit management mode" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create target" })).not.toBeInTheDocument();
    expect(createMonitorTarget).not.toHaveBeenCalled();
  });

  it("loads and pages manual and health resources independently", async () => {
    const user = userEvent.setup();
    render(<MonitorPage />);
    await waitFor(() => expect(screen.getAllByText("Page 1 of 2 · 75 items")).toHaveLength(2));
    expect(listMonitorTargets).toHaveBeenCalledWith({ page: 1, page_size: 50 });
    expect(getMonitorTargetHealth).toHaveBeenCalledWith({ page: 1, page_size: 50 });

    const pagers = screen.getAllByRole("navigation", { name: "Pagination" });
    await user.click(within(pagers[0]).getByRole("button", { name: "Next" }));
    await waitFor(() => expect(getMonitorTargetHealth).toHaveBeenCalledWith({ page: 2, page_size: 50 }));
    expect(listMonitorTargets).toHaveBeenCalledTimes(1);
    await user.click(within(pagers[1]).getByRole("button", { name: "Next" }));
    await waitFor(() => expect(listMonitorTargets).toHaveBeenCalledWith({ page: 2, page_size: 50 }));
  });

  it("resets only the manual page when filters change and retains rows while it loads", async () => {
    let resolveManual!: (value: ReturnType<typeof manualPage>) => void;
    vi.mocked(listMonitorTargets).mockResolvedValueOnce(manualPage(2)).mockImplementationOnce(() => new Promise((resolve) => { resolveManual = resolve; }));
    render(<MonitorPage />);
    await screen.findByText("000001");
    await userEvent.selectOptions(screen.getByLabelText("Market filter"), "A");

    expect(listMonitorTargets).toHaveBeenLastCalledWith({ market: "A", page: 1, page_size: 50 });
    expect(screen.getByText("000001")).toBeInTheDocument();
    expect(getMonitorTargetHealth).toHaveBeenCalledTimes(1);
    resolveManual(manualPage());
  });

  it("adopts canonical pages and keeps each table's loading controls independent", async () => {
    let resolveHealth!: (value: ReturnType<typeof healthPage>) => void;
    vi.mocked(listMonitorTargets).mockResolvedValueOnce(manualPage()).mockResolvedValueOnce(manualPage()).mockResolvedValueOnce(manualPage());
    vi.mocked(getMonitorTargetHealth).mockResolvedValueOnce(healthPage()).mockImplementationOnce(() => new Promise((resolve) => { resolveHealth = resolve; }));
    const user = userEvent.setup();
    render(<MonitorPage />);
    await waitFor(() => expect(screen.getAllByRole("navigation", { name: "Pagination" })).toHaveLength(2));
    const pagers = screen.getAllByRole("navigation", { name: "Pagination" });
    await user.click(within(pagers[0]).getByRole("button", { name: "Next" }));
    await waitFor(() => expect(getMonitorTargetHealth).toHaveBeenLastCalledWith({ page: 2, page_size: 50 }));
    expect(within(screen.getAllByRole("navigation", { name: "Pagination" })[0]).getByRole("button", { name: "Next" })).toBeDisabled();
    expect(within(screen.getAllByRole("navigation", { name: "Pagination" })[1]).getByRole("button", { name: "Next" })).toBeEnabled();
    await user.click(within(screen.getAllByRole("navigation", { name: "Pagination" })[1]).getByRole("button", { name: "Next" }));
    await waitFor(() => expect(listMonitorTargets).toHaveBeenCalledWith({ page: 2, page_size: 50 }));
    await waitFor(() => expect(listMonitorTargets).toHaveBeenLastCalledWith({ page: 1, page_size: 50 }));
    await act(async () => { resolveHealth(healthPage()); });
  });

  it("writes back canonical pages for manual and health resources", async () => {
    vi.mocked(listMonitorTargets).mockResolvedValue(manualPage(2));
    vi.mocked(getMonitorTargetHealth).mockResolvedValue(healthPage(2));
    render(<MonitorPage />);

    await waitFor(() => expect(screen.getAllByText("Page 2 of 2 · 75 items")).toHaveLength(2));
    expect(listMonitorTargets).toHaveBeenLastCalledWith({ page: 2, page_size: 50 });
    expect(getMonitorTargetHealth).toHaveBeenLastCalledWith({ page: 2, page_size: 50 });
  });

  it("refreshes mutations at the current pages and adopts canonical pages after deletion", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(listMonitorTargets).mockResolvedValue(manualPage(2));
    vi.mocked(getMonitorTargetHealth).mockResolvedValue(healthPage(2));
    render(<MonitorPage />);
    await waitFor(() => expect(screen.getAllByText("Page 2 of 2 · 75 items")).toHaveLength(2));
    vi.mocked(listMonitorTargets).mockClear();
    vi.mocked(getMonitorTargetHealth).mockClear();
    vi.mocked(listMonitorTargets).mockResolvedValue(manualPage(1));
    vi.mocked(getMonitorTargetHealth).mockResolvedValue(healthPage(1));
    vi.mocked(deleteMonitorTarget).mockResolvedValue(undefined);

    await user.click(screen.getByRole("button", { name: "Enter management mode" }));
    await user.click(screen.getByRole("button", { name: "Delete 000001" }));
    await waitFor(() => expect(deleteMonitorTarget).toHaveBeenCalledWith(17));
    expect(listMonitorTargets).toHaveBeenNthCalledWith(1, { page: 2, page_size: 50 });
    expect(getMonitorTargetHealth).toHaveBeenNthCalledWith(1, { page: 2, page_size: 50 });
    await waitFor(() => expect(screen.getAllByText("Page 1 of 2 · 75 items")).toHaveLength(2));
  });

  it("ignores stale manual responses after a newer filter request", async () => {
    let resolveStale!: (value: ReturnType<typeof manualPage>) => void;
    const freshTarget = { ...target, stock_code: "000002" };
    vi.mocked(listMonitorTargets).mockImplementationOnce(() => new Promise((resolve) => { resolveStale = resolve; })).mockResolvedValueOnce({ ...manualPage(), items: [freshTarget] });
    const user = userEvent.setup();
    render(<MonitorPage />);

    await user.selectOptions(screen.getByLabelText("Market filter"), "A");
    expect(await screen.findByText("000002")).toBeInTheDocument();
    await act(async () => { resolveStale(manualPage()); });
    expect(screen.queryByText("000001")).not.toBeInTheDocument();
  });

  it("ignores stale health responses after refresh", async () => {
    let resolveStale!: (value: ReturnType<typeof healthPage>) => void;
    const staleHealth = healthPage();
    const freshHealth = { ...healthPage(), items: [{ ...healthPage().items[0], stock_code: "fresh-workflow" }] };
    vi.mocked(getMonitorTargetHealth).mockImplementationOnce(() => new Promise((resolve) => { resolveStale = resolve; })).mockResolvedValueOnce(freshHealth);
    const user = userEvent.setup();
    render(<MonitorPage />);

    await waitFor(() => expect(getMonitorTargetHealth).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole("button", { name: "Refresh targets" }));
    expect(await screen.findByText("fresh-workflow")).toBeInTheDocument();
    await act(async () => { resolveStale(staleHealth); });
    expect(screen.queryByText("workflow-only")).not.toBeInTheDocument();
    expect(screen.getByText("fresh-workflow")).toBeInTheDocument();
  });

  it("keeps health visible when manual loading fails", async () => {
    vi.mocked(listMonitorTargets).mockRejectedValue(new Error("Manual service unavailable"));
    render(<MonitorPage />);

    expect(await screen.findByText("workflow-only")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("Manual service unavailable");
  });

  it("keeps manual rows visible when health loading fails", async () => {
    vi.mocked(getMonitorTargetHealth).mockRejectedValue(new Error("Health service unavailable"));
    render(<MonitorPage />);

    expect(await screen.findByText("000001")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("Health service unavailable");
  });

  it("keeps management mode through create, edit, toggle, delete, and dialog close", async () => {
    const user = userEvent.setup();
    vi.mocked(createMonitorTarget).mockResolvedValue(target);
    vi.mocked(updateMonitorTarget).mockResolvedValue(target);
    vi.mocked(setMonitorTargetEnabled).mockResolvedValue({ ...target, enabled: false });
    vi.mocked(deleteMonitorTarget).mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<MonitorPage />);
    await screen.findByText("000001");
    await user.click(screen.getByRole("button", { name: "Enter management mode" }));

    await user.click(screen.getByRole("button", { name: "Create target" }));
    await user.click(screen.getByRole("button", { name: "Close editor" }));
    expect(screen.getByRole("button", { name: "Exit management mode" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create target" }));
    await user.type(screen.getByLabelText("Stock code"), "000002");
    await user.click(screen.getByRole("dialog").querySelector('button[type="submit"]')!);
    await waitFor(() => expect(createMonitorTarget).toHaveBeenCalled());
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.click(screen.getByRole("dialog").querySelector('button[type="submit"]')!);
    await waitFor(() => expect(updateMonitorTarget).toHaveBeenCalled());
    await user.click(screen.getByRole("button", { name: "Disable 000001" }));
    await waitFor(() => expect(setMonitorTargetEnabled).toHaveBeenCalled());
    await user.click(screen.getByRole("button", { name: "Delete 000001" }));
    await waitFor(() => expect(deleteMonitorTarget).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "Exit management mode" })).toBeInTheDocument();
  });
});
