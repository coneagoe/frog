import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createAccount, deleteAccount, listAccounts, listCashLedger, listPositions } from "@/lib/api-client";
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
  listAccounts: vi.fn(),
  listPositions: vi.fn(),
  listCashLedger: vi.fn()
}));

const createAccountMock = vi.mocked(createAccount);
const deleteAccountMock = vi.mocked(deleteAccount);
const listAccountsMock = vi.mocked(listAccounts);
const listPositionsMock = vi.mocked(listPositions);
const listCashLedgerMock = vi.mocked(listCashLedger);

const demoAccount = { id: 1, name: "demo", initial_cash: "100000.00", status: "active", base_currency: "CNY" };

describe("AccountsPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockSearchParams.delete("accountId");
  });

  it("renders existing accounts", async () => {
    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([]);
    listCashLedgerMock.mockResolvedValue([]);

    render(<AccountsPage />);

    expect(await screen.findByText("demo")).toBeInTheDocument();
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
    listCashLedgerMock.mockResolvedValue([]);
    createAccountMock.mockResolvedValue(demoAccount);

    render(<AccountsPage />);
    await userEvent.type(await screen.findByLabelText("Account name"), "demo");
    await userEvent.clear(screen.getByLabelText("Initial cash"));
    await userEvent.type(screen.getByLabelText("Initial cash"), "100000.00");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(createAccountMock).toHaveBeenCalledWith({ name: "demo", initial_cash: "100000.00" });
    await waitFor(() => expect(listAccountsMock).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("demo")).toBeInTheDocument();
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
    listCashLedgerMock.mockResolvedValue([]);
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
    listCashLedgerMock.mockResolvedValue([]);
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
    listCashLedgerMock.mockResolvedValue([]);
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
    const account2 = { id: 2, name: "prod", initial_cash: "50000.00", status: "active", base_currency: "CNY" };
    listAccountsMock
      .mockResolvedValueOnce([demoAccount, account2])
      .mockResolvedValueOnce([account2]);
    listPositionsMock.mockResolvedValue([]);
    listCashLedgerMock.mockResolvedValue([]);
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
      expect(listCashLedgerMock).toHaveBeenCalledWith(2);
    });
    expect(screen.getByText("Positions")).toBeInTheDocument();
    expect(screen.queryByText("No paper accounts yet")).not.toBeInTheDocument();
  });

  it("loads positions and cash ledger for the first account on initial load", async () => {
    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([
      { symbol: "000001", total_quantity: 100, frozen_quantity: 0, cost_amount: "5000.00", realized_pnl: "200.00" }
    ]);
    listCashLedgerMock.mockResolvedValue([
      { id: 1, account_id: 1, event_type: "deposit", amount: "100000.00", note: "Initial deposit" }
    ]);

    render(<AccountsPage />);

    // Wait for the first account to be auto-selected and Positions panel to render
    expect(await screen.findByText("Positions")).toBeInTheDocument();
    expect(listPositionsMock).toHaveBeenCalledWith(1);
    expect(listCashLedgerMock).toHaveBeenCalledWith(1);
    expect(screen.getByText("Cash Ledger")).toBeInTheDocument();
  });

  it("switches positions and cash ledger when selecting a different account", async () => {
    const account2 = { id: 2, name: "prod", initial_cash: "50000.00", status: "active", base_currency: "CNY" };
    listAccountsMock.mockResolvedValue([demoAccount, account2]);
    listPositionsMock.mockResolvedValue([]);
    listCashLedgerMock.mockResolvedValue([]);

    render(<AccountsPage />);

    expect(await screen.findByText("prod")).toBeInTheDocument();

    // Click View on the second account
    await userEvent.click(screen.getByRole("button", { name: "View prod" }));

    // Wait for the Positions panel to appear for account 2
    expect(await screen.findByText("Positions")).toBeInTheDocument();
    expect(listPositionsMock).toHaveBeenCalledWith(2);
    expect(listCashLedgerMock).toHaveBeenCalledWith(2);
  });

  it("renders fulfilled tables and shows error banner when detail loading partially fails", async () => {
    listAccountsMock.mockResolvedValue([demoAccount]);
    listPositionsMock.mockResolvedValue([
      { symbol: "000001", total_quantity: 100, frozen_quantity: 0, cost_amount: "5000.00", realized_pnl: "200.00" }
    ]);
    listCashLedgerMock.mockRejectedValue(new Error("Ledger unavailable"));

    render(<AccountsPage />);

    // Both tables should render even with partial failure
    expect(await screen.findByText("Positions")).toBeInTheDocument();
    // Positions data should be visible
    expect(screen.getByText("000001")).toBeInTheDocument();
    // Cash Ledger table should still render (even if empty/errored)
    expect(screen.getByText("Cash Ledger")).toBeInTheDocument();
    // Error banner should be visible for the failed portion
    expect(screen.getByRole("alert")).toHaveTextContent("Ledger unavailable");
  });

  it("selects account from valid ?accountId search param", async () => {
    // Set accountId=2 which is valid
    mockSearchParams.set("accountId", "2");
    const account2 = { id: 2, name: "prod", initial_cash: "50000.00", status: "active", base_currency: "CNY" };
    listAccountsMock.mockResolvedValue([demoAccount, account2]);
    listPositionsMock.mockResolvedValue([]);
    listCashLedgerMock.mockResolvedValue([]);

    render(<AccountsPage />);

    // Should select account 2, not account 1
    await waitFor(() => {
      expect(listPositionsMock).toHaveBeenCalledWith(2);
      expect(listCashLedgerMock).toHaveBeenCalledWith(2);
    });
    expect(screen.getByText("Positions")).toBeInTheDocument();
  });

  it("falls back to first account when ?accountId is invalid", async () => {
    // Set accountId=999 which doesn't exist
    mockSearchParams.set("accountId", "999");
    const account2 = { id: 2, name: "prod", initial_cash: "50000.00", status: "active", base_currency: "CNY" };
    listAccountsMock.mockResolvedValue([demoAccount, account2]);
    listPositionsMock.mockResolvedValue([]);
    listCashLedgerMock.mockResolvedValue([]);

    render(<AccountsPage />);

    // Should fall back to first account (id=1)
    await waitFor(() => {
      expect(listPositionsMock).toHaveBeenCalledWith(1);
      expect(listCashLedgerMock).toHaveBeenCalledWith(1);
    });
    expect(screen.getByText("Positions")).toBeInTheDocument();
  });

  it("manual View selection wins over unchanged ?accountId URL param", async () => {
    // User visits /accounts?accountId=1, then clicks View for account 2
    // Account 2 should remain selected, not reverted to account 1
    mockSearchParams.set("accountId", "1");
    const account2 = { id: 2, name: "prod", initial_cash: "50000.00", status: "active", base_currency: "CNY" };
    listAccountsMock.mockResolvedValue([demoAccount, account2]);
    listPositionsMock.mockResolvedValue([]);
    listCashLedgerMock.mockResolvedValue([]);

    render(<AccountsPage />);

    // Account 1 auto-selected from URL param
    await waitFor(() => {
      expect(listPositionsMock).toHaveBeenCalledWith(1);
    });
    expect(screen.getByText("Positions")).toBeInTheDocument();

    // Clear call counts so we can detect new calls
    listPositionsMock.mockClear();
    listCashLedgerMock.mockClear();

    // Click View for account 2
    await userEvent.click(screen.getByRole("button", { name: "View prod" }));

    // Account 2 should be selected and its details loaded
    await waitFor(() => {
      expect(listPositionsMock).toHaveBeenCalledWith(2);
      expect(listCashLedgerMock).toHaveBeenCalledWith(2);
    });
    // Account 2 should remain selected, not reverted to account 1
    // listPositions should NOT have been called with 1 again
    expect(listPositionsMock).not.toHaveBeenCalledWith(1);
    expect(listCashLedgerMock).not.toHaveBeenCalledWith(1);
  });

  it("updates selected account when ?accountId changes to a different valid account", async () => {
    const account2 = { id: 2, name: "prod", initial_cash: "50000.00", status: "active", base_currency: "CNY" };
    listAccountsMock.mockResolvedValue([demoAccount, account2]);
    listPositionsMock.mockResolvedValue([]);
    listCashLedgerMock.mockResolvedValue([]);

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
});
