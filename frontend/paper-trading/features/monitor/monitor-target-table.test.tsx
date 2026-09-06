import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MonitorTargetTable } from "./monitor-target-table";

const target = { id: 17, stock_code: "000001", market: "A" as const, frequency: "daily" as const, reset_mode: "auto" as const, enabled: true, last_state: false, triggered_at: null, created_at: null, note: null, condition: { type: "price_threshold" as const, direction: "above" as const, value: 10 } };
const otherTarget = { ...target, id: 18, stock_code: "000002" };

describe("MonitorTargetTable", () => {
  it("disables every action on the busy target while leaving other targets operable", () => {
    render(<MonitorTargetTable targets={[target, otherTarget]} busyTargetIds={new Set([target.id])} onEdit={vi.fn()} onToggle={vi.fn()} onDelete={vi.fn()} />);

    expect(screen.getAllByRole("button", { name: "Edit" })[0]).toBeDisabled();
    expect(screen.getByRole("button", { name: "Disable 000001" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Delete 000001" })).toBeDisabled();
    expect(screen.getAllByRole("button", { name: "Edit" })[1]).toBeEnabled();
    expect(screen.getByRole("button", { name: "Disable 000002" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Delete 000002" })).toBeEnabled();
  });

  it("disables a row for any in-flight action", () => {
    render(<MonitorTargetTable targets={[target]} busyTargetIds={new Set([target.id])} onEdit={vi.fn()} onToggle={vi.fn()} onDelete={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Edit" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Disable 000001" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Delete 000001" })).toBeDisabled();
  });
});
