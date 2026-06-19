import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createAccount, deleteAccount, listAccounts } from "@/lib/api-client";
import { AccountsPage } from "./accounts-page";

vi.mock("@/lib/api-client", () => ({
  createAccount: vi.fn(),
  deleteAccount: vi.fn(),
  listAccounts: vi.fn()
}));

const createAccountMock = vi.mocked(createAccount);
const deleteAccountMock = vi.mocked(deleteAccount);
const listAccountsMock = vi.mocked(listAccounts);

describe("AccountsPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("renders existing accounts", async () => {
    listAccountsMock.mockResolvedValue([
      { id: 1, name: "demo", initial_cash: "100000.00", status: "active", base_currency: "CNY" }
    ]);

    render(<AccountsPage />);

    expect(await screen.findByText("demo")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Trade" })).toHaveAttribute("href", "/trade?accountId=1");
    expect(screen.getByRole("link", { name: "Analytics" })).toHaveAttribute("href", "/analytics?accountId=1");
  });

  it("creates an account and refreshes the list", async () => {
    listAccountsMock
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        { id: 1, name: "demo", initial_cash: "100000.00", status: "active", base_currency: "CNY" }
      ]);
    createAccountMock.mockResolvedValue({
      id: 1,
      name: "demo",
      initial_cash: "100000.00",
      status: "active",
      base_currency: "CNY"
    });

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
      .mockResolvedValueOnce([
        { id: 1, name: "demo", initial_cash: "100000.00", status: "active", base_currency: "CNY" }
      ])
      .mockResolvedValueOnce([]);
    deleteAccountMock.mockResolvedValue(undefined);
    const confirmMock = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<AccountsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete demo" }));

    expect(confirmMock).toHaveBeenCalledWith("Delete paper account demo? This permanently removes all related trading data.");
    expect(deleteAccountMock).toHaveBeenCalledWith(1);
    await waitFor(() => expect(listAccountsMock).toHaveBeenCalledTimes(2));
    expect(screen.getByText("No paper accounts yet")).toBeInTheDocument();
  });

  it("does not delete an account when confirmation is cancelled", async () => {
    listAccountsMock.mockResolvedValue([
      { id: 1, name: "demo", initial_cash: "100000.00", status: "active", base_currency: "CNY" }
    ]);
    vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<AccountsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete demo" }));

    expect(deleteAccountMock).not.toHaveBeenCalled();
    expect(listAccountsMock).toHaveBeenCalledTimes(1);
  });
});
