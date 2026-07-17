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

  it("shows the import workspace title and selected account context", () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    expect(screen.getByRole("dialog", { name: "Import initial positions for demo" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Import initial positions" })).toBeInTheDocument();
    expect(screen.getByText("Account: demo")).toBeInTheDocument();
  });

  it("starts with one editable row", () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    expect(screen.getAllByLabelText("Symbol")).toHaveLength(1);
  });

  it("shows visible YYYY-MM-DD guidance on the buy date input", () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    expect(screen.getByLabelText("Buy trade date")).toHaveAttribute("placeholder", "YYYY-MM-DD");
    expect(screen.getByText("YYYY-MM-DD", { selector: "small" })).toBeInTheDocument();
  });

  it("renders one aligned import grid header and row", () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    const grid = screen.getByTestId("import-positions-grid");
    expect(within(grid).getAllByText("Symbol")).toHaveLength(2);
    expect(within(grid).getAllByText("Quantity")).toHaveLength(2);
    expect(within(grid).getAllByText("Cost price")).toHaveLength(2);
    expect(within(grid).getAllByText("Buy date")).toHaveLength(2);
    expect(within(grid).getAllByTestId("import-position-row")).toHaveLength(1);
  });

  it("shows concise import guidance before the editable grid", () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    expect(screen.getByText("Set starting holdings for this account. Cash will not change.")).toBeInTheDocument();
    expect(screen.getByText("Use this once for an empty account.")).toBeInTheDocument();
    expect(screen.getByText("Lots with the same symbol are allowed.")).toBeInTheDocument();
    expect(screen.getByText("Importing positions does not add or remove cash.")).toBeInTheDocument();
  });

  it("adding a row increases the number of row groups", async () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    expect(screen.getAllByLabelText("Symbol")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Add row" }));
    expect(screen.getAllByLabelText("Symbol")).toHaveLength(2);
  });

  it("updates the footer row count as rows are added", async () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    expect(screen.getByText("1 row ready for input")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add row" }));
    expect(screen.getByText("2 rows ready for input")).toBeInTheDocument();
  });

  it("removing a row does not leave the table visually empty", async () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: "Add row" }));
    expect(screen.getAllByLabelText("Symbol")).toHaveLength(2);

    const removeButtons = screen.getAllByRole("button", { name: "Remove row" });
    await userEvent.click(removeButtons[0]);
    expect(screen.getAllByLabelText("Symbol")).toHaveLength(1);
  });

  it("removing the only row keeps at least one row", async () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    expect(screen.getAllByLabelText("Symbol")).toHaveLength(1);

    await userEvent.click(screen.getByRole("button", { name: "Remove row" }));
    expect(screen.getAllByLabelText("Symbol")).toHaveLength(1);
  });

  it("blank cost price shows a validation alert and does not submit", async () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    await userEvent.type(screen.getByLabelText("Symbol"), "000001");
    await userEvent.type(screen.getByLabelText("Quantity"), "100");
    // cost_price left empty
    await userEvent.type(screen.getByLabelText("Buy trade date"), "2026-01-15");

    await userEvent.click(screen.getByRole("button", { name: "Import positions" }));

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(importPositionsMock).not.toHaveBeenCalled();
  });

  it("shows specific message when backend rejects with already has positions", async () => {
    importPositionsMock.mockRejectedValue(new Error("Account already has positions"));

    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    const dialog = screen.getByRole("dialog", { name: "Import initial positions for demo" });
    await userEvent.type(within(dialog).getByLabelText("Symbol"), "000001");
    await userEvent.type(within(dialog).getByLabelText("Quantity"), "100");
    await userEvent.type(within(dialog).getByLabelText("Cost price"), "10.23");
    await userEvent.type(within(dialog).getByLabelText("Buy trade date"), "2026-01-15");

    await userEvent.click(screen.getByRole("button", { name: "Import positions" }));

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(
      "This account already has positions. Import is only available for empty accounts."
    );
  });

  it("submits a valid import payload", async () => {
    importPositionsMock.mockResolvedValue({ imported_count: 1, lots_count: 1 });

    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    const dialog = screen.getByRole("dialog", { name: "Import initial positions for demo" });
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
