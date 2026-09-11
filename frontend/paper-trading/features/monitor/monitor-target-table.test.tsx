import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MonitorTargetTable } from "./monitor-target-table";

const target = { id: 17, stock_code: "000001", stock_name: "Ping An Bank", market: "A" as const, frequency: "daily" as const, reset_mode: "auto" as const, enabled: true, last_state: false, triggered_at: null, created_at: null, note: null, condition: { type: "price_threshold" as const, direction: "above" as const, value: 10 } };
const props = { busyTargetIds: new Set<number>(), loading: false, page: 2, totalCount: 75, totalPages: 2, sort: "default", onSort: vi.fn(), onPreviousPage: vi.fn(), onNextPage: vi.fn(), onEdit: vi.fn(), onToggle: vi.fn(), onDelete: vi.fn() };

describe("MonitorTargetTable", () => {
  it("is read-only by default and displays the target name", () => {
    render(<MonitorTargetTable {...props} managementMode={false} targets={[target, { ...target, id: 18, stock_name: null }]} />);

    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByText("Actions")).not.toBeInTheDocument();
    expect(screen.getByText("Ping An Bank")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.getByText("Page 2 of 2 · 75 items")).toBeInTheDocument();
  });

  it("shows actions only for manageable rows and disables a busy row", () => {
    render(<MonitorTargetTable {...props} busyTargetIds={new Set([target.id])} managementMode targets={[{ ...target, can_manage: true }]} />);

    expect(screen.getByRole("button", { name: /Edit 000001/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Disable 000001/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Delete 000001/ })).toBeDisabled();
  });

  it("shows backend operational state separately from the triggered marker", () => {
    render(<MonitorTargetTable {...props} managementMode={false} targets={[{ ...target, enabled: true, last_state: true, operational_state: "paused" }]} />);

    expect(screen.getByText("Paused")).toBeInTheDocument();
    expect(screen.getByText(/Triggered/)).toBeInTheDocument();
    expect(screen.queryByText("Running")).not.toBeInTheDocument();
  });

  it("shows no pagination for a single page and disables only its controls while loading", () => {
    const { rerender } = render(<MonitorTargetTable {...props} loading managementMode={false} targets={[target]} />);
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();

    rerender(<MonitorTargetTable {...props} managementMode={false} targets={[target]} totalPages={1} />);
    expect(screen.queryByRole("navigation", { name: "Pagination" })).not.toBeInTheDocument();
  });
});
