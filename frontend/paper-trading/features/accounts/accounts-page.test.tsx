import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createAccount, deleteAccount, depositCash, importPositions, listAccounts, listPositions, updateAccountFees, withdrawCash } from "@/lib/api-client";
import { AccountsPage } from "./accounts-page";

// Return the same URLSearchParams instance across renders for stable references.
// For URL-change tests, mutate the instance before a remount.
const mockSearchParams = vi.hoisted(() => new URLSearchParams());
vi.mock("next/navigation", () => ({
  useSearchParams: () => mockSearchParams
}));

vi.mock("@/lib/api-client", () => ({
  createAccount: vi.fn(),
  deleteAccount: vi.fn(),
  depositCash: vi.fn(),
  importPositions: vi.fn(),
  listAccounts: vi.fn(),
  listPositions: vi.fn(),
  updateAccountFees: vi.fn(),
  withdrawCash: vi.fn()
}));

const createAccountMock = vi.mocked(createAccount);
const deleteAccountMock = vi.mocked(deleteAccount);
const depositCashMock = vi.mocked(depositCash);
const importPositionsMock = vi.mocked(importPositions);
const listAccountsMock = vi.mocked(listAccounts);
const listPositionsMock = vi.mocked(listPositions);
const updateAccountFeesMock = vi.mocked(updateAccountFees);
const withdrawCashMock = vi.mocked(withdrawCash);

const demoAccount = {
  id: 1,
  name: "demo",
  initial_cash: "100000.00",
  cash_available: "100000.0000",
  status: "active",
  base_currency: "CNY",
  fee_preset: "a_share",
  commission_rate: "0.000300",
  min_commission: "5.00",
  stamp_duty_rate: "0.000500",
  transfer_fee_rate: "0.000010",
  share_count: "100000.000000",
  net_asset_value: "1.000000",
  cumulative_deposit: "100000.0000",
  cumulative_withdrawal: "0.0000"
};

describe("AccountsPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockSearchParams.delete("accountId");
  });

  it("renders existing accounts", async () => {
    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([]);

    render(<AccountsPage />);

    expect(await screen.findByText("demo")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Accounts" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: "Paper Accounts" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Initial Cash" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Fees" })).not.toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Trade" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Analytics" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete demo" })).toBeInTheDocument();
  });

  it("uses the accounts-specific two-column layout", async () => {
    listAccountsMock.mockResolvedValue([]);

    const { container } = render(<AccountsPage />);

    expect(await screen.findByText("No paper accounts yet")).toBeInTheDocument();
    expect(container.querySelector(".accounts-grid")).toHaveClass("grid", "grid--two", "accounts-grid");
  });

  it("creates an account and refreshes the list", async () => {
    listAccountsMock
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([demoAccount]);
    listPositionsMock.mockResolvedValue([]);
    createAccountMock.mockResolvedValue(demoAccount);

    render(<AccountsPage />);
    await userEvent.type(await screen.findByLabelText("Account name"), "demo");
    await userEvent.clear(screen.getByLabelText("Initial cash"));
    await userEvent.type(screen.getByLabelText("Initial cash"), "100000.00");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(createAccountMock).toHaveBeenCalledWith({ name: "demo", initial_cash: "100000.00" });
    await waitFor(() => expect(listAccountsMock).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("cell", { name: "demo" })).toBeInTheDocument();
  });

  it("creates an account with custom fee settings", async () => {
    listAccountsMock
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([demoAccount]);
    listPositionsMock.mockResolvedValue([]);
    createAccountMock.mockResolvedValue(demoAccount);

    render(<AccountsPage />);
    await userEvent.type(await screen.findByLabelText("Account name"), "demo");
    await userEvent.clear(screen.getByLabelText("Commission rate (%)"));
    await userEvent.type(screen.getByLabelText("Commission rate (%)"), "0.02");
    await userEvent.clear(screen.getByLabelText("Minimum commission (CNY)"));
    await userEvent.type(screen.getByLabelText("Minimum commission (CNY)"), "3.00");
    await userEvent.clear(screen.getByLabelText("Stamp duty rate (%)"));
    await userEvent.type(screen.getByLabelText("Stamp duty rate (%)"), "0.05");
    await userEvent.clear(screen.getByLabelText("Transfer fee rate (%)"));
    await userEvent.type(screen.getByLabelText("Transfer fee rate (%)"), "0.001");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(createAccountMock).toHaveBeenCalledWith({
      name: "demo",
      initial_cash: "100000.00",
      fee_preset: "a_share",
      commission_rate: "0.0002",
      min_commission: "3.00",
      stamp_duty_rate: "0.0005",
      transfer_fee_rate: "0.00001"
    });
  });

  it("converts 0.57 percent to 0.0057 decimal rate on create", async () => {
    listAccountsMock.mockResolvedValue([]);
    createAccountMock.mockResolvedValue(demoAccount);

    render(<AccountsPage />);
    await userEvent.type(await screen.findByLabelText("Account name"), "demo");
    await userEvent.clear(screen.getByLabelText("Commission rate (%)"));
    await userEvent.type(screen.getByLabelText("Commission rate (%)"), "0.57");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(createAccountMock).toHaveBeenCalledWith({
      name: "demo",
      initial_cash: "100000.00",
      fee_preset: "a_share",
      commission_rate: "0.0057",
      min_commission: "5.00",
      stamp_duty_rate: "0.0005",
      transfer_fee_rate: "0.00001"
    });
  });

  it("omits blank optional fee fields when creating an account", async () => {
    listAccountsMock.mockResolvedValue([]);
    createAccountMock.mockResolvedValue(demoAccount);

    render(<AccountsPage />);
    await userEvent.type(await screen.findByLabelText("Account name"), "demo");
    await userEvent.clear(screen.getByLabelText("Commission rate (%)"));
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(createAccountMock).toHaveBeenCalledWith({
      name: "demo",
      initial_cash: "100000.00",
      fee_preset: "a_share",
      min_commission: "5.00",
      stamp_duty_rate: "0.0005",
      transfer_fee_rate: "0.00001"
    });
  });

  it("rejects negative fee settings before submitting", async () => {
    listAccountsMock.mockResolvedValue([]);

    render(<AccountsPage />);
    await userEvent.type(await screen.findByLabelText("Account name"), "demo");
    await userEvent.clear(screen.getByLabelText("Commission rate (%)"));
    await userEvent.type(screen.getByLabelText("Commission rate (%)"), "-0.01");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Fee settings must be non-negative numbers");
    expect(createAccountMock).not.toHaveBeenCalled();
  });

  it("rejects exponent notation like 1e-3 in fee fields on create", async () => {
    listAccountsMock.mockResolvedValue([]);

    render(<AccountsPage />);
    await userEvent.type(await screen.findByLabelText("Account name"), "demo");
    await userEvent.clear(screen.getByLabelText("Commission rate (%)"));
    await userEvent.type(screen.getByLabelText("Commission rate (%)"), "1e-3");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Fee settings must be non-negative numbers");
    expect(createAccountMock).not.toHaveBeenCalled();
  });

  it("keeps account fee details out of the account list", async () => {
    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([]);

    render(<AccountsPage />);

    expect(await screen.findByText("demo")).toBeInTheDocument();
    const accountTable = screen.getByRole("table");
    expect(within(accountTable).queryByText("¥100,000.00")).not.toBeInTheDocument();
    expect(within(accountTable).queryByText("A-share default")).not.toBeInTheDocument();
    expect(within(accountTable).queryByText("Commission 0.000300, min 5.00")).not.toBeInTheDocument();
  });

  it("shows backend errors", async () => {
    listAccountsMock.mockResolvedValue([]);
    createAccountMock.mockRejectedValue(new Error("Account already exists"));

    render(<AccountsPage />);
    await userEvent.type(await screen.findByLabelText("Account name"), "demo");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Account already exists");
  });

  it("deletes an account after confirmation and refreshes the list", async () => {
    listAccountsMock
      .mockResolvedValueOnce([demoAccount])
      .mockResolvedValueOnce([]);
    listPositionsMock.mockResolvedValue([]);
    deleteAccountMock.mockResolvedValue(undefined);
    const confirmMock = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<AccountsPage />);
    // Wait for initial auto-select so Positions panel renders
    expect(await screen.findByText("Positions")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete demo" }));

    expect(confirmMock).toHaveBeenCalledWith("Delete paper account demo? This permanently removes all related trading data.");
    expect(deleteAccountMock).toHaveBeenCalledWith(1);
    await waitFor(() => expect(listAccountsMock).toHaveBeenCalledTimes(2));
    expect(screen.getByText("No paper accounts yet")).toBeInTheDocument();
    // Detail panels should be cleared when last account is deleted
    expect(screen.queryByText("Positions")).not.toBeInTheDocument();
    expect(screen.queryByText("Cash Ledger")).not.toBeInTheDocument();
  });

  it("does not delete an account when confirmation is cancelled", async () => {
    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([]);
    vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<AccountsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete demo" }));

    expect(deleteAccountMock).not.toHaveBeenCalled();
    expect(listAccountsMock).toHaveBeenCalledTimes(1);
  });

  it("clears detail panels when the last account is deleted", async () => {
    listAccountsMock
      .mockResolvedValueOnce([demoAccount])
      .mockResolvedValueOnce([]);
    listPositionsMock.mockResolvedValue([]);
    deleteAccountMock.mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<AccountsPage />);

    // Initial load: demo auto-selected, Positions panel visible
    expect(await screen.findByText("Positions")).toBeInTheDocument();

    // Delete the only account
    await userEvent.click(screen.getByRole("button", { name: "Delete demo" }));
    await waitFor(() => expect(listAccountsMock).toHaveBeenCalledTimes(2));

    // Detail panels should disappear
    expect(screen.queryByText("Positions")).not.toBeInTheDocument();
    expect(screen.queryByText("Cash Ledger")).not.toBeInTheDocument();
    expect(screen.getByText("No paper accounts yet")).toBeInTheDocument();
  });

  it("re-selects the first valid account after deleting the selected account", async () => {
    const account2 = { ...demoAccount, id: 2, name: "prod", initial_cash: "50000.00", cash_available: "50000.0000" };
    listAccountsMock
      .mockResolvedValueOnce([demoAccount, account2])
      .mockResolvedValueOnce([account2]);
    listPositionsMock.mockResolvedValue([]);
    deleteAccountMock.mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<AccountsPage />);

    // Initial load: demo is auto-selected
    expect(await screen.findByText("Positions")).toBeInTheDocument();
    expect(listPositionsMock).toHaveBeenCalledWith(1);

    // Delete demo (currently selected)
    await userEvent.click(screen.getByRole("button", { name: "Delete demo" }));
    await waitFor(() => expect(listAccountsMock).toHaveBeenCalledTimes(2));

    // The remaining account (prod) should be auto-selected and its details loaded
    await waitFor(() => {
      expect(listPositionsMock).toHaveBeenCalledWith(2);
    });
    expect(screen.getByText("Positions")).toBeInTheDocument();
    expect(screen.queryByText("No paper accounts yet")).not.toBeInTheDocument();
  });

  it("loads positions without requesting the cash ledger for the first account on initial load", async () => {
    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([
      { symbol: "000001", stock_name: "Ping An Bank", total_quantity: 100, frozen_quantity: 0, cost_amount: "5000.00", realized_pnl: "200.00", mark_price: "12.50", price_source: "real_time", unrealized_pnl: "250.00" }
    ]);

    render(<AccountsPage />);

    // Wait for the first account to be auto-selected and Positions panel to render
    expect(await screen.findByText("Positions")).toBeInTheDocument();
    expect(listPositionsMock).toHaveBeenCalledWith(1);
    expect(screen.queryByText("Cash Ledger")).not.toBeInTheDocument();
  });

  it("uses a compact table for account positions", async () => {
    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([
      { symbol: "000001", stock_name: "Ping An Bank", total_quantity: 100, frozen_quantity: 0, cost_amount: "5000.00", realized_pnl: "200.00", mark_price: "12.50", price_source: "real_time", unrealized_pnl: "250.00" }
    ]);

    const { container } = render(<AccountsPage />);

    expect(await screen.findByText("Positions")).toBeInTheDocument();
    const compactTables = container.querySelectorAll(".table.table--compact");
    expect(compactTables).toHaveLength(1);
    expect(container.querySelectorAll(".table-wrap.table-wrap--compact")).toHaveLength(1);
  });

  it("switches positions without requesting the cash ledger when selecting a different account", async () => {
    const account2 = {
      ...demoAccount,
      id: 2,
      name: "prod",
      initial_cash: "50000.00",
      cash_available: "50000.0000",
      net_asset_value: "2.000000",
      share_count: "50000.000000"
    };
    listAccountsMock.mockResolvedValue([demoAccount, account2]);
    listPositionsMock.mockResolvedValue([
      { symbol: "000001", stock_name: "Ping An Bank", total_quantity: 100, frozen_quantity: 0, cost_amount: "1000.00", realized_pnl: "0.00", mark_price: "12.50", price_source: "real_time" as const, unrealized_pnl: "0.00" }
    ]);

    render(<AccountsPage />);

    expect(await screen.findByText("prod")).toBeInTheDocument();

    // Click View on the second account
    await userEvent.click(screen.getByRole("button", { name: "View prod" }));

    // Wait for the Positions panel to appear for account 2
    expect(await screen.findByText("Positions")).toBeInTheDocument();
    expect(listPositionsMock).toHaveBeenCalledWith(2);
    expect(screen.getByRole("cell", { name: "1.25%" })).toBeInTheDocument();
  });

  it("resets position sorting when switching accounts", async () => {
    const account2 = { ...demoAccount, id: 2, name: "prod", initial_cash: "50000.00", cash_available: "50000.0000" };
    const account1Positions = [
      { symbol: "000001", stock_name: "Ping An Bank", total_quantity: 100, frozen_quantity: 0, cost_amount: "5000.00", realized_pnl: "0.00", mark_price: "12.50", price_source: "real_time", unrealized_pnl: "250.00" },
      { symbol: "000002", stock_name: "Vanke", total_quantity: 200, frozen_quantity: 10, cost_amount: "4000.00", realized_pnl: "0.00", mark_price: "8.00", price_source: "real_time", unrealized_pnl: "-100.00" }
    ];
    const account2Positions = [
      { symbol: "000003", stock_name: "China Merchants Bank", total_quantity: 300, frozen_quantity: 0, cost_amount: "3000.00", realized_pnl: "0.00", mark_price: "10.00", price_source: "real_time", unrealized_pnl: "100.00" },
      { symbol: "000004", stock_name: "Midea", total_quantity: 400, frozen_quantity: 0, cost_amount: "2000.00", realized_pnl: "0.00", mark_price: "5.00", price_source: "real_time", unrealized_pnl: "50.00" }
    ];
    listAccountsMock.mockResolvedValue([demoAccount, account2]);
    listPositionsMock.mockImplementation(async (accountId) => accountId === 1 ? account1Positions : account2Positions);

    render(<AccountsPage />);
    const positions = within((await screen.findByRole("heading", { name: "Positions" })).closest("section")!);
    await userEvent.click(positions.getByRole("button", { name: "Symbol" }));
    await userEvent.click(positions.getByRole("button", { name: "Symbol" }));
    expect(positions.getAllByRole("row")[1]).toHaveTextContent("000002");

    await userEvent.click(screen.getByRole("button", { name: "View prod" }));
    await waitFor(() => expect(positions.getAllByRole("row")[1]).toHaveTextContent("000003"));
    expect(positions.getAllByRole("row")[2]).toHaveTextContent("000004");
  });

  it("renders positions without a detail error when the request succeeds", async () => {
    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([
      { symbol: "000001", stock_name: "Ping An Bank", total_quantity: 100, frozen_quantity: 0, cost_amount: "5000.00", realized_pnl: "200.00", mark_price: "12.50", price_source: "real_time", unrealized_pnl: "250.00" }
    ]);

    render(<AccountsPage />);

    expect(await screen.findByText("Positions")).toBeInTheDocument();
    expect(screen.getByText("000001")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders compact positions columns in backend order", async () => {
    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([
      { symbol: "000001", stock_name: "Ping An Bank", total_quantity: 100, frozen_quantity: 0, cost_amount: "5000.00", realized_pnl: "200.00", mark_price: "12.50", price_source: "real_time", unrealized_pnl: "250.00" },
      { symbol: "000002", stock_name: "Vanke", total_quantity: 200, frozen_quantity: 10, cost_amount: "4000.00", realized_pnl: "100.00", mark_price: "8.00", price_source: "real_time", unrealized_pnl: "-100.00" }
    ]);

    render(<AccountsPage />);

    const positions = within((await screen.findByRole("heading", { name: "Positions" })).closest("section")!);
    expect(positions.getAllByRole("columnheader").map((header) => header.textContent)).toEqual([
      "Symbol",
      "Stock",
      "Total",
      "Frozen",
      "Weight",
      "Return"
    ]);
    expect(positions.queryByRole("columnheader", { name: "Cost" })).not.toBeInTheDocument();
    expect(positions.queryByRole("columnheader", { name: "Unrealized PnL" })).not.toBeInTheDocument();
    expect(positions.getAllByRole("row").slice(1).map((row) => within(row).getAllByRole("cell").map((cell) => cell.textContent).join(""))).toEqual([
      "000001Ping An Bank10001.25%+5.00%",
      "000002Vanke200101.60%-2.50%"
    ]);
  });

  it("formats position returns and marks unavailable values", async () => {
    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([
      { symbol: "POSITIVE", stock_name: "Positive", total_quantity: 1, frozen_quantity: 0, cost_amount: "5000.00", realized_pnl: "999999.00", mark_price: "1.00", price_source: "real_time", unrealized_pnl: "250.00" },
      { symbol: "NEGATIVE", stock_name: "Negative", total_quantity: 1, frozen_quantity: 0, cost_amount: "4000.00", realized_pnl: "-999999.00", mark_price: "1.00", price_source: "real_time", unrealized_pnl: "-100.00" },
      { symbol: "ZERO", stock_name: "Zero", total_quantity: 1, frozen_quantity: 0, cost_amount: "3000.00", realized_pnl: "500.00", mark_price: "1.00", price_source: "real_time", unrealized_pnl: "0.00" },
      { symbol: "NO-COST", stock_name: "No cost", total_quantity: 1, frozen_quantity: 0, cost_amount: "0.00", realized_pnl: "0.00", mark_price: "1.00", price_source: "real_time", unrealized_pnl: "1.00" },
      { symbol: "NO-PNL", stock_name: "No pnl", total_quantity: 1, frozen_quantity: 0, cost_amount: "1000.00", realized_pnl: "0.00", mark_price: "1.00", price_source: "real_time", unrealized_pnl: null },
      { symbol: "INVALID", stock_name: "Invalid", total_quantity: 1, frozen_quantity: 0, cost_amount: "not-a-number", realized_pnl: "0.00", mark_price: "1.00", price_source: "real_time", unrealized_pnl: "1.00" },
      { symbol: "INFINITE", stock_name: "Infinite", total_quantity: 1, frozen_quantity: 0, cost_amount: "1000.00", realized_pnl: "0.00", mark_price: "1.00", price_source: "real_time", unrealized_pnl: "Infinity" }
    ]);

    render(<AccountsPage />);

    const positions = within((await screen.findByRole("heading", { name: "Positions" })).closest("section")!);
    const rows = positions.getAllByRole("row").slice(1);
    const returnCell = (row: HTMLElement) => within(row).getAllByRole("cell")[5];
    expect(within(returnCell(rows[0])).getByText("+5.00%")).toHaveClass("positive");
    expect(within(returnCell(rows[1])).getByText("-2.50%")).toHaveClass("negative");
    expect(within(returnCell(rows[2])).getByText("0.00%")).toHaveClass("default");
    expect(within(returnCell(rows[3])).getByText("—")).toHaveClass("muted");
    expect(within(returnCell(rows[4])).getByText("—")).toHaveClass("muted");
    expect(within(returnCell(rows[5])).getByText("—")).toHaveClass("muted");
    expect(within(returnCell(rows[6])).getByText("—")).toHaveClass("muted");
    expect(returnCell(rows[0])).toHaveClass("numeric");
    expect(positions.getByRole("columnheader", { name: "Return" })).toHaveClass("numeric");
  });

  it("selects account from valid ?accountId search param", async () => {
    // Set accountId=2 which is valid
    mockSearchParams.set("accountId", "2");
    const account2 = { ...demoAccount, id: 2, name: "prod", initial_cash: "50000.00", cash_available: "50000.0000" };
    listAccountsMock.mockResolvedValue([demoAccount, account2]);
    listPositionsMock.mockResolvedValue([]);

    render(<AccountsPage />);

    // Should select account 2, not account 1
    await waitFor(() => {
      expect(listPositionsMock).toHaveBeenCalledWith(2);
    });
    expect(screen.getByText("Positions")).toBeInTheDocument();
  });

  it("falls back to first account when ?accountId is invalid", async () => {
    // Set accountId=999 which doesn't exist
    mockSearchParams.set("accountId", "999");
    const account2 = { ...demoAccount, id: 2, name: "prod", initial_cash: "50000.00", cash_available: "50000.0000" };
    listAccountsMock.mockResolvedValue([demoAccount, account2]);
    listPositionsMock.mockResolvedValue([]);

    render(<AccountsPage />);

    // Should fall back to first account (id=1)
    await waitFor(() => {
      expect(listPositionsMock).toHaveBeenCalledWith(1);
    });
    expect(screen.getByText("Positions")).toBeInTheDocument();
  });

  it("manual View selection wins over unchanged ?accountId URL param", async () => {
    // User visits /accounts?accountId=1, then clicks View for account 2
    // Account 2 should remain selected, not reverted to account 1
    mockSearchParams.set("accountId", "1");
    const account2 = { ...demoAccount, id: 2, name: "prod", initial_cash: "50000.00", cash_available: "50000.0000" };
    listAccountsMock.mockResolvedValue([demoAccount, account2]);
    listPositionsMock.mockResolvedValue([]);

    render(<AccountsPage />);

    // Account 1 auto-selected from URL param
    await waitFor(() => {
      expect(listPositionsMock).toHaveBeenCalledWith(1);
    });
    expect(screen.getByText("Positions")).toBeInTheDocument();

    // Clear call counts so we can detect new calls
    listPositionsMock.mockClear();

    // Click View for account 2
    await userEvent.click(screen.getByRole("button", { name: "View prod" }));

    // Account 2 should be selected and its details loaded
    await waitFor(() => {
      expect(listPositionsMock).toHaveBeenCalledWith(2);
    });
    // Account 2 should remain selected, not reverted to account 1
    // listPositions should NOT have been called with 1 again
    expect(listPositionsMock).not.toHaveBeenCalledWith(1);
  });

  it("updates selected account when ?accountId changes to a different valid account", async () => {
    const account2 = { ...demoAccount, id: 2, name: "prod", initial_cash: "50000.00", cash_available: "50000.0000" };
    listAccountsMock.mockResolvedValue([demoAccount, account2]);
    listPositionsMock.mockResolvedValue([]);

    // Render with accountId=1
    mockSearchParams.set("accountId", "1");
    const { unmount } = render(<AccountsPage />);

    // Account 1 loads
    await waitFor(() => {
      expect(listPositionsMock).toHaveBeenCalledWith(1);
    });

    // Simulate URL change to accountId=2 via unmount/remount (full navigation)
    unmount();
    mockSearchParams.delete("accountId");
    mockSearchParams.set("accountId", "2");
    render(<AccountsPage />);

    // Account 2's details should be loaded
    await waitFor(() => {
      expect(listPositionsMock).toHaveBeenCalledWith(2);
    });
  });

  it("opens the fee editor from the selected account header", async () => {
    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([]);

    render(<AccountsPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Edit fees" }));

    const dialog = screen.getByRole("dialog", { name: "Edit fees for demo" });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Commission rate (%)")).toHaveValue("0.03");
  });

  it("saves fee changes and refreshes account data", async () => {
    const updatedAccount = { ...demoAccount, commission_rate: "0.0002" };
    listAccountsMock.mockResolvedValueOnce([demoAccount]).mockResolvedValueOnce([updatedAccount]);
    listPositionsMock.mockResolvedValue([]);
    updateAccountFeesMock.mockResolvedValue(updatedAccount);

    render(<AccountsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit fees" }));
    const dialog = screen.getByRole("dialog", { name: "Edit fees for demo" });
    await userEvent.clear(within(dialog).getByLabelText("Commission rate (%)"));
    await userEvent.type(within(dialog).getByLabelText("Commission rate (%)"), "0.02");
    await userEvent.click(screen.getByRole("button", { name: "Save fees" }));

    expect(updateAccountFeesMock).toHaveBeenCalledWith(1, { commission_rate: "0.0002" });
    await waitFor(() => expect(listAccountsMock).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("dialog", { name: "Edit fees for demo" })).not.toBeInTheDocument();
  });

  it("displays decimal rate 0.0057 as percent 0.57 in the fee editor", async () => {
    const account0057 = { ...demoAccount, commission_rate: "0.005700" };
    listAccountsMock.mockResolvedValue([account0057]);
    listPositionsMock.mockResolvedValue([]);

    render(<AccountsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit fees" }));

    const dialog = screen.getByRole("dialog", { name: "Edit fees for demo" });
    expect(within(dialog).getByLabelText("Commission rate (%)")).toHaveValue("0.57");
  });

  it("saves 0.57 percent as 0.0057 decimal rate in the fee editor", async () => {
    const updatedAccount = { ...demoAccount, commission_rate: "0.0057" };
    listAccountsMock.mockResolvedValueOnce([demoAccount]).mockResolvedValueOnce([updatedAccount]);
    listPositionsMock.mockResolvedValue([]);
    updateAccountFeesMock.mockResolvedValue(updatedAccount);

    render(<AccountsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit fees" }));
    const dialog = screen.getByRole("dialog", { name: "Edit fees for demo" });
    await userEvent.clear(within(dialog).getByLabelText("Commission rate (%)"));
    await userEvent.type(within(dialog).getByLabelText("Commission rate (%)"), "0.57");
    await userEvent.click(screen.getByRole("button", { name: "Save fees" }));

    expect(updateAccountFeesMock).toHaveBeenCalledWith(1, { commission_rate: "0.0057" });
  });

  it("does not reload saved account details when that account is no longer selected", async () => {
    const account2 = { ...demoAccount, id: 2, name: "prod", initial_cash: "50000.00", cash_available: "50000.0000" };
    const updatedAccount = { ...demoAccount, commission_rate: "0.0002" };

    // Control when the fee update resolves so we can switch accounts mid-save
    let resolveUpdate!: (value: unknown) => void;
    updateAccountFeesMock.mockImplementation(() => new Promise((resolve) => { resolveUpdate = resolve; }));

    listAccountsMock.mockResolvedValue([demoAccount, account2]);
    listPositionsMock.mockResolvedValue([]);

    render(<AccountsPage />);
    expect(await screen.findByText("Positions")).toBeInTheDocument();

    // Open fee editor for demo (account 1)
    await userEvent.click(screen.getByRole("button", { name: "Edit fees" }));
    const dialog = screen.getByRole("dialog", { name: "Edit fees for demo" });
    expect(dialog).toBeInTheDocument();

    // Change a field and click Save (save is pending because of the deferred promise)
    await userEvent.clear(within(dialog).getByLabelText("Commission rate (%)"));
    await userEvent.type(within(dialog).getByLabelText("Commission rate (%)"), "0.02");
    await userEvent.click(screen.getByRole("button", { name: "Save fees" }));

    // While the save is pending, switch to account 2
    await userEvent.click(screen.getByRole("button", { name: "View prod" }));
    expect(listPositionsMock).toHaveBeenCalledWith(2);

    // Clear call counts so we can detect any stale calls for account 1
    listPositionsMock.mockClear();

    // Let the save complete
    resolveUpdate(updatedAccount);

    // After save completes, details for account 1 should NOT be reloaded
    await waitFor(() => {
      expect(listPositionsMock).not.toHaveBeenCalledWith(1);
    });
  });

  it("shows validation errors without sending an empty patch", async () => {
    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([]);

    render(<AccountsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit fees" }));
    await userEvent.click(screen.getByRole("button", { name: "Save fees" }));

    expect(updateAccountFeesMock).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Change at least one fee field before saving.");
  });

  it("shows an Import positions button on the selected account panel", async () => {
    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([]);

    render(<AccountsPage />);

    expect(await screen.findByText("Positions")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import positions" })).toBeInTheDocument();
  });

  it("opens the import modal with a one-time import note", async () => {
    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([]);

    render(<AccountsPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Import positions" }));

    const dialog = screen.getByRole("dialog", { name: "Import initial positions for demo" });
    expect(within(dialog).getByText(/set starting holdings for this account/i)).toBeInTheDocument();
  });

  it("imports positions, shows success message, closes modal, and refreshes account details", async () => {
    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([]);
    importPositionsMock.mockResolvedValue({ imported_count: 2, lots_count: 5 });

    render(<AccountsPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Import positions" }));
    const dialog = screen.getByRole("dialog", { name: "Import initial positions for demo" });
    await userEvent.type(within(dialog).getByLabelText("Symbol"), "000001");
    await userEvent.type(within(dialog).getByLabelText("Quantity"), "100");
    await userEvent.type(within(dialog).getByLabelText("Cost price"), "10.23");
    await userEvent.type(within(dialog).getByLabelText("Buy trade date"), "2026-01-15");
    await userEvent.click(within(dialog).getByRole("button", { name: "Import positions" }));

    expect(importPositionsMock).toHaveBeenCalledWith(1, {
      positions: [{ symbol: "000001", quantity: 100, cost_price: "10.23", buy_trade_date: "2026-01-15", market: "a_share" }]
    });
    await waitFor(() => expect(listPositionsMock).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("dialog", { name: "Import initial positions for demo" })).not.toBeInTheDocument();

    const success = screen.getByRole("status");
    expect(success).toHaveTextContent("Imported 2 positions across 5 lots.");
  });

  it("clears the success message when opening the import modal again", async () => {
    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([]);
    importPositionsMock.mockResolvedValue({ imported_count: 1, lots_count: 1 });

    render(<AccountsPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Import positions" }));
    const dialog = screen.getByRole("dialog", { name: "Import initial positions for demo" });
    await userEvent.type(within(dialog).getByLabelText("Symbol"), "000001");
    await userEvent.type(within(dialog).getByLabelText("Quantity"), "100");
    await userEvent.type(within(dialog).getByLabelText("Cost price"), "10.23");
    await userEvent.type(within(dialog).getByLabelText("Buy trade date"), "2026-01-15");
    await userEvent.click(within(dialog).getByRole("button", { name: "Import positions" }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Imported 1 position across 1 lot."));

    // Open the modal again — success message should disappear
    await userEvent.click(screen.getByRole("button", { name: "Import positions" }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("clears the success message when selecting a different account", async () => {
    const account2 = { ...demoAccount, id: 2, name: "prod", initial_cash: "50000.00", cash_available: "50000.0000" };
    listAccountsMock.mockResolvedValue([demoAccount, account2]);
    listPositionsMock.mockResolvedValue([]);
    importPositionsMock.mockResolvedValue({ imported_count: 1, lots_count: 1 });

    render(<AccountsPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Import positions" }));
    const dialog = screen.getByRole("dialog", { name: "Import initial positions for demo" });
    await userEvent.type(within(dialog).getByLabelText("Symbol"), "000001");
    await userEvent.type(within(dialog).getByLabelText("Quantity"), "100");
    await userEvent.type(within(dialog).getByLabelText("Cost price"), "10.23");
    await userEvent.type(within(dialog).getByLabelText("Buy trade date"), "2026-01-15");
    await userEvent.click(within(dialog).getByRole("button", { name: "Import positions" }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Imported 1 position across 1 lot."));

    // Switch to a different account
    await userEvent.click(screen.getByRole("button", { name: "View prod" }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("shows backend validation errors without closing the modal", async () => {
    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([]);
    importPositionsMock.mockRejectedValue(new Error("Account already has positions"));

    render(<AccountsPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Import positions" }));
    const dialog = screen.getByRole("dialog", { name: "Import initial positions for demo" });
    await userEvent.type(within(dialog).getByLabelText("Symbol"), "000001");
    await userEvent.type(within(dialog).getByLabelText("Quantity"), "100");
    await userEvent.type(within(dialog).getByLabelText("Cost price"), "10.23");
    await userEvent.type(within(dialog).getByLabelText("Buy trade date"), "2026-01-15");
    await userEvent.click(within(dialog).getByRole("button", { name: "Import positions" }));

    expect(importPositionsMock).toHaveBeenCalled();
    await waitFor(() => {
      expect(within(dialog).getByRole("alert")).toHaveTextContent(
        "This account already has positions. Import is only available for empty accounts."
      );
    });
    expect(dialog).toBeInTheDocument();
  });

  it("shows Deposit and Withdraw buttons on the selected account panel", async () => {
    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([]);

    render(<AccountsPage />);

    expect(await screen.findByText("Positions")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Deposit" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Withdraw" })).toBeInTheDocument();
  });

  it("opens deposit modal from the Deposit button", async () => {
    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([]);

    render(<AccountsPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Deposit" }));

    const dialog = screen.getByRole("dialog", { name: "Deposit cash for demo" });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Deposit" })).toBeInTheDocument();
  });

  it("opens withdraw modal from the Withdraw button", async () => {
    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([]);

    render(<AccountsPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Withdraw" }));

    const dialog = screen.getByRole("dialog", { name: "Withdraw cash from demo" });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Withdraw" })).toBeInTheDocument();
  });

  it("submits a deposit from the account page and refreshes", async () => {
    const ledgerEntry = { id: 1, account_id: 1, event_type: "deposit", amount: "100000.0000", note: "Initial deposit", trade_date: null, net_asset_value: null, share_delta: null };

    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([]);
    depositCashMock.mockResolvedValue({
      account_id: 1,
      cash_available: "110000.0000",
      net_asset_value: "1.000000",
      share_count: "110000.000000",
      ledger: { ...ledgerEntry, id: 2, amount: "10000.0000", note: "add", event_type: "deposit" }
    });

    render(<AccountsPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Deposit" }));
    const dialog = screen.getByRole("dialog", { name: "Deposit cash for demo" });
    await userEvent.type(within(dialog).getByLabelText("Amount"), "10000");
    await userEvent.clear(within(dialog).getByLabelText("Trade date"));
    await userEvent.type(within(dialog).getByLabelText("Trade date"), "2026-07-20");
    await userEvent.type(within(dialog).getByLabelText("Note"), "add");
    await userEvent.click(within(dialog).getByRole("button", { name: "Deposit" }));

    expect(depositCashMock).toHaveBeenCalledWith(1, { amount: "10000", trade_date: "2026-07-20", note: "add" });
    await waitFor(() => {
      expect(listAccountsMock).toHaveBeenCalledTimes(2);
    });
    expect(screen.queryByRole("dialog", { name: "Deposit cash for demo" })).not.toBeInTheDocument();
  });
});
