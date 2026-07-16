import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { importPositions } from "@/lib/api-client";
import { ImportPositionsModal } from "./import-positions-modal";

const importPositionsMock = vi.mocked(importPositions);

vi.mock("@/lib/api-client", () => ({
  importPositions: vi.fn()
}));

const demoAccount = {
  id: 1,
  name: "demo",
  initial_cash: "100000.00",
  status: "active",
  base_currency: "CNY",
  fee_preset: "a_share",
  commission_rate: "0.000300",
  min_commission: "5.00",
  stamp_duty_rate: "0.000500",
  transfer_fee_rate: "0.000010"
};

describe("ImportPositionsModal", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("shows the title Import positions for demo", () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    expect(screen.getByRole("dialog", { name: "Import positions for demo" })).toBeInTheDocument();
  });

  it("starts with one editable row", () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    expect(screen.getAllByLabelText("Symbol")).toHaveLength(1);
  });

  it("shows the note that import is one-time and does not change cash", () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    expect(
      screen.getByText("Importing initializes existing holdings only and does not change cash.")
    ).toBeInTheDocument();
  });

  it("adding a row increases the number of row groups", async () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    expect(screen.getAllByLabelText("Symbol")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Add row" }));
    expect(screen.getAllByLabelText("Symbol")).toHaveLength(2);
  });

  it("removing a row does not leave the table visually empty", async () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: "Add row" }));
    expect(screen.getAllByLabelText("Symbol")).toHaveLength(2);

    const removeButtons = screen.getAllByRole("button", { name: "Remove row" });
    await userEvent.click(removeButtons[0]);
    expect(screen.getAllByLabelText("Symbol")).toHaveLength(1);
  });

  it("submits a valid import payload", async () => {
    importPositionsMock.mockResolvedValue({ imported_count: 1, lots_count: 1 });

    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    const dialog = screen.getByRole("dialog", { name: "Import positions for demo" });
    await userEvent.type(within(dialog).getByLabelText("Symbol"), "000001");
    await userEvent.type(within(dialog).getByLabelText("Quantity"), "100");
    await userEvent.type(within(dialog).getByLabelText("Cost price"), "10.23");
    await userEvent.type(within(dialog).getByLabelText("Buy trade date"), "2026-01-15");

    await userEvent.click(screen.getByRole("button", { name: "Import positions" }));

    expect(importPositionsMock).toHaveBeenCalledWith(1, {
      positions: [{ symbol: "000001", quantity: 100, cost_price: "10.23", buy_trade_date: "2026-01-15" }]
    });
  });

  it("invalid quantity shows a validation alert and does not submit", async () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    await userEvent.type(screen.getByLabelText("Symbol"), "000001");
    await userEvent.type(screen.getByLabelText("Quantity"), "0");
    await userEvent.type(screen.getByLabelText("Cost price"), "10.23");
    await userEvent.type(screen.getByLabelText("Buy trade date"), "2026-01-15");

    await userEvent.click(screen.getByRole("button", { name: "Import positions" }));

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(importPositionsMock).not.toHaveBeenCalled();
  });

  it("invalid date shows a validation alert and does not submit", async () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    await userEvent.type(screen.getByLabelText("Symbol"), "000001");
    await userEvent.type(screen.getByLabelText("Quantity"), "100");
    await userEvent.type(screen.getByLabelText("Cost price"), "10.23");
    await userEvent.type(screen.getByLabelText("Buy trade date"), "bad-date");

    await userEvent.click(screen.getByRole("button", { name: "Import positions" }));

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(importPositionsMock).not.toHaveBeenCalled();
  });
});
