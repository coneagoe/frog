import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MonitorTargetFormModal } from "./monitor-target-form-modal";

describe("MonitorTargetFormModal", () => {
  it("creates a target and clears an empty note", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<MonitorTargetFormModal open target={null} onClose={vi.fn()} onSubmit={onSubmit} />);
    await userEvent.type(screen.getByLabelText("Stock code"), "000001");
    await userEvent.type(screen.getByLabelText("Note"), "temporary");
    await userEvent.clear(screen.getByLabelText("Note"));
    await userEvent.click(screen.getByRole("button", { name: "Create target" }));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ stock_code: "000001", note: null }));
  });

  it("prevents an invalid close-cross-MA edit after scope changes", async () => {
    const onSubmit = vi.fn();
    render(<MonitorTargetFormModal open target={{ id: 17, stock_code: "000001", market: "A", frequency: "daily", reset_mode: "auto", enabled: true, last_state: false, triggered_at: null, created_at: null, note: null, condition: { type: "close_cross_ma", direction: "above", period: 20 } }} onClose={vi.fn()} onSubmit={onSubmit} />);
    await userEvent.selectOptions(screen.getByLabelText("Market"), "HK");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Close crosses MA is available for daily A-share targets only");
  });

  it("edits an existing target and sends a cleared note as null", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<MonitorTargetFormModal open target={{ id: 17, stock_code: "000001", market: "A", frequency: "daily", reset_mode: "auto", enabled: true, last_state: false, triggered_at: null, created_at: null, note: "remove me", condition: { type: "price_threshold", direction: "above", value: 10 } }} onClose={vi.fn()} onSubmit={onSubmit} />);
    await userEvent.clear(screen.getByLabelText("Note"));
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ stock_code: "000001", note: null }));
  });
});
