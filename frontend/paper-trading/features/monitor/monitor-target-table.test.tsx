import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MonitorTargetTable } from "./monitor-target-table";

const target = { id: 17, stock_code: "000001", market: "A" as const, frequency: "daily" as const, reset_mode: "auto" as const, enabled: true, last_state: false, triggered_at: null, created_at: null, note: null, condition: { type: "price_threshold" as const, direction: "above" as const, value: 10 } };

describe("MonitorTargetTable", () => {
  it("disables only the action currently running and leaves Edit available", () => {
    render(<MonitorTargetTable targets={[target]} busyAction={{ id: target.id, type: "toggle" }} onEdit={vi.fn()} onToggle={vi.fn()} onDelete={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Edit" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Disable 000001" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Delete 000001" })).toBeEnabled();
  });

  it("disables Delete without disabling toggle or Edit", () => {
    render(<MonitorTargetTable targets={[target]} busyAction={{ id: target.id, type: "delete" }} onEdit={vi.fn()} onToggle={vi.fn()} onDelete={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Edit" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Disable 000001" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Delete 000001" })).toBeDisabled();
  });
});
