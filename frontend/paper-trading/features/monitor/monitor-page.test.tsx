import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { deleteMonitorTarget, listMonitorTargets, setMonitorTargetEnabled } from "@/lib/api-client";
import { MonitorPage } from "./monitor-page";

vi.mock("@/lib/api-client", () => ({ listMonitorTargets: vi.fn(), createMonitorTarget: vi.fn(), updateMonitorTarget: vi.fn(), setMonitorTargetEnabled: vi.fn(), deleteMonitorTarget: vi.fn() }));
const target = { id: 17, stock_code: "000001", market: "A" as const, frequency: "daily" as const, reset_mode: "auto" as const, enabled: true, last_state: false, triggered_at: null, created_at: null, note: "watch", condition: { type: "price_threshold" as const, direction: "above" as const, value: 10 } };

describe("MonitorPage", () => {
  beforeEach(() => vi.resetAllMocks());
  it("filters by all four supported fields and has no workflow controls", async () => {
    vi.mocked(listMonitorTargets).mockResolvedValue([]);
    render(<MonitorPage />);
    await screen.findByText("No manual monitor targets yet");
    await userEvent.selectOptions(screen.getByLabelText("Market filter"), "A");
    await userEvent.selectOptions(screen.getByLabelText("Frequency filter"), "daily");
    await userEvent.selectOptions(screen.getByLabelText("Status filter"), "true");
    await userEvent.selectOptions(screen.getByLabelText("Condition filter"), "rsi");
    expect(listMonitorTargets).toHaveBeenLastCalledWith({ market: "A", frequency: "daily", enabled: true, condition_type: "rsi" });
    expect(screen.queryByText(/pause|resume/i)).not.toBeInTheDocument();
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
