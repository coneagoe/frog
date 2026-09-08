import { useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api-error";
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

  it("uses a right-side editor panel while retaining dialog focus management", async () => {
    render(<MonitorTargetFormModal open target={null} onClose={vi.fn()} onSubmit={vi.fn()} />);

    const dialog = screen.getByRole("dialog", { name: "Create monitor target" });
    expect(dialog).toHaveClass("monitor-editor-panel");
    expect(dialog.parentElement).toHaveClass("monitor-editor-backdrop");
    expect(screen.getByRole("button", { name: "Close editor" })).toBeInTheDocument();
  });

  it("shows field errors for an invalid stock code and numeric condition", async () => {
    const onSubmit = vi.fn();
    render(<MonitorTargetFormModal open target={null} onClose={vi.fn()} onSubmit={onSubmit} />);
    await userEvent.type(screen.getByLabelText("Stock code"), "abc");
    await userEvent.clear(screen.getByLabelText("Value"));
    await userEvent.click(screen.getByRole("button", { name: "Create target" }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText("Enter a valid 6-digit A-share code.")).toBeInTheDocument();
    expect(screen.getByText("Enter a number greater than 0.")).toBeInTheDocument();
    expect(screen.getByLabelText("Stock code")).toHaveAttribute("aria-invalid", "true");
  });

  it("validates MA relationships, periods, and RSI ranges before saving", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<MonitorTargetFormModal open target={null} onClose={vi.fn()} onSubmit={onSubmit} />);
    await user.type(screen.getByLabelText("Stock code"), "000001");
    await user.selectOptions(screen.getByLabelText("Condition type"), "ma_cross");
    await user.clear(screen.getByLabelText("Fast period"));
    await user.type(screen.getByLabelText("Fast period"), "20");
    await user.clear(screen.getByLabelText("Slow period"));
    await user.type(screen.getByLabelText("Slow period"), "5");
    await user.click(screen.getByRole("button", { name: "Create target" }));
    expect(screen.getByText("Fast period must be less than slow period.")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Condition type"), "rsi");
    await user.clear(screen.getByLabelText("RSI value"));
    await user.type(screen.getByLabelText("RSI value"), "101");
    await user.click(screen.getByRole("button", { name: "Create target" }));
    expect(screen.getByText("RSI value must be between 0 and 100.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("maps API field errors to their corresponding input", async () => {
    const onSubmit = vi.fn().mockRejectedValue(new ApiError(422, "VALIDATION_ERROR", "Invalid target", { field: "stock_code", message: "This code is already monitored." }));
    render(<MonitorTargetFormModal open target={null} onClose={vi.fn()} onSubmit={onSubmit} />);
    await waitFor(() => expect(screen.getByLabelText("Stock code")).toHaveValue(""));
    await userEvent.type(screen.getByLabelText("Stock code"), "000001");
    await userEvent.click(screen.getByRole("button", { name: "Create target" }));

    expect(await screen.findByText("This code is already monitored.")).toBeInTheDocument();
    expect(screen.getByLabelText("Stock code")).toHaveAttribute("aria-invalid", "true");
  });

  it("edits an existing target and sends a cleared note as null", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<MonitorTargetFormModal open target={{ id: 17, stock_code: "000001", market: "A", frequency: "daily", reset_mode: "auto", enabled: true, last_state: false, triggered_at: null, created_at: null, note: "remove me", condition: { type: "price_threshold", direction: "above", value: 10 } }} onClose={vi.fn()} onSubmit={onSubmit} />);
    await userEvent.clear(screen.getByLabelText("Note"));
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ stock_code: "000001", note: null }));
  });

  it("moves focus into the dialog, traps Tab, closes on Escape, and restores its invoker", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    function TestModal() { const [open, setOpen] = useState(false); return <><button type="button" onClick={() => setOpen(true)}>Open target form</button><MonitorTargetFormModal open={open} target={null} onClose={() => { onClose(); setOpen(false); }} onSubmit={vi.fn()} /></>; }
    render(<TestModal />);
    const invoker = screen.getByRole("button", { name: "Open target form" });
    await user.click(invoker);

    await waitFor(() => expect(screen.getByLabelText("Stock code")).toHaveFocus());
    await user.tab({ shift: true });
    expect(screen.getByRole("button", { name: "Close editor" })).toHaveFocus();
    await user.tab();
    expect(screen.getByLabelText("Stock code")).toHaveFocus();
    await user.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(invoker).toHaveFocus();
  });

  it("does not close on Escape while saving", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    let resolveSubmit!: () => void;
    const onSubmit = vi.fn(() => new Promise<void>((resolve) => { resolveSubmit = resolve; }));
    render(<MonitorTargetFormModal open target={null} onClose={onClose} onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText("Stock code"), "000001");
    await user.click(screen.getByRole("button", { name: "Create target" }));
    await screen.findByRole("button", { name: "Saving…" });
    await user.keyboard("{Escape}");

    expect(onClose).not.toHaveBeenCalled();
    resolveSubmit();
    await waitFor(() => expect(screen.getByRole("button", { name: "Create target" })).toBeEnabled());
  });
});
