import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cancelOrder, listAccounts, listOrders } from "@/lib/api-client";
import { OrdersPage } from "./orders-page";

const mockSearchParams = vi.hoisted(() => new URLSearchParams());
vi.mock("next/navigation", () => ({
  useSearchParams: () => mockSearchParams
}));

vi.mock("@/lib/api-client", () => ({
  listAccounts: vi.fn(),
  listOrders: vi.fn(),
  cancelOrder: vi.fn()
}));

const listAccountsMock = vi.mocked(listAccounts);
const listOrdersMock = vi.mocked(listOrders);
const cancelOrderMock = vi.mocked(cancelOrder);

const mockAccount = { id: 1, name: "demo", initial_cash: "100000.00", status: "active", base_currency: "CNY" };
const mockOrder = {
  id: 42,
  account_id: 1,
  symbol: "AAPL",
  side: "buy" as const,
  quantity: 100,
  limit_price: "150.00",
  trade_date: "2026-06-27",
  status: "accepted",
  filled_quantity: 0,
  frozen_cash: "15000.00",
  frozen_quantity: 100,
  rejection_code: null,
  rejection_reason: null
};

describe("OrdersPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("loads the first account, fetches orders, and renders an order row", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue([mockOrder]);

    render(<OrdersPage />);

    expect(await screen.findByText("Orders")).toBeInTheDocument();
    expect(await screen.findByText("AAPL")).toBeInTheDocument();
    // listAccounts must be called at least once
    expect(listAccountsMock.mock.calls.length).toBeGreaterThanOrEqual(1);
    // listOrders must be called with the first account id
    expect(listOrdersMock.mock.calls.some(call => call[0] === 1)).toBe(true);
  });

  it("calls cancelOrder when clicking Cancel", async () => {
    const user = userEvent.setup();
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue([mockOrder]);
    cancelOrderMock.mockResolvedValue({ ...mockOrder, status: "cancelled" });

    render(<OrdersPage />);

    expect(await screen.findByText("Cancel")).toBeInTheDocument();
    await user.click(screen.getByText("Cancel"));

    expect(cancelOrderMock).toHaveBeenCalledWith(42);
  });

  it("refreshes listOrders after cancellation", async () => {
    const user = userEvent.setup();
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue([mockOrder]);
    cancelOrderMock.mockResolvedValue({ ...mockOrder, status: "cancelled" });

    render(<OrdersPage />);

    expect(await screen.findByText("Cancel")).toBeInTheDocument();
    const callsBefore = listOrdersMock.mock.calls.length;
    expect(callsBefore).toBeGreaterThanOrEqual(1);

    await user.click(screen.getByText("Cancel"));

    await waitFor(() => {
      expect(listOrdersMock.mock.calls.length).toBe(callsBefore + 1);
    });
  });

  it("shows ErrorBanner when cancellation fails", async () => {
    const user = userEvent.setup();
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue([mockOrder]);
    cancelOrderMock.mockRejectedValue(new Error("Order cannot be cancelled"));

    render(<OrdersPage />);

    expect(await screen.findByText("Cancel")).toBeInTheDocument();
    await user.click(screen.getByText("Cancel"));

    // flush promises so the rejection is handled by handleCancel
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Order cannot be cancelled");
    }, { timeout: 5000 });
  });

  it("clears orders before fetching a different account", async () => {
    const user = userEvent.setup();
    let resolveOrders!: (value: unknown) => void;
    const ordersPromise = new Promise<typeof mockOrder[]>((resolve) => { resolveOrders = resolve; });

    const secondAccount = { id: 2, name: "test2", initial_cash: "100000.00", status: "active", base_currency: "CNY" };
    listAccountsMock.mockResolvedValue([mockAccount, secondAccount]);
    listOrdersMock.mockResolvedValue([mockOrder]);

    render(<OrdersPage />);
    expect(await screen.findByText("AAPL")).toBeInTheDocument();

    // Defer Account 2's order fetch so we can observe the cleared state
    listOrdersMock.mockReturnValue(ordersPromise);

    // Switch to Account 2 — orders should clear before the deferred fetch completes
    await user.selectOptions(screen.getByLabelText("Account"), "2");

    // Old orders should be gone even though the new fetch hasn't resolved
    await waitFor(() => {
      expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
    });

    // Now let the deferred fetch resolve with new orders
    resolveOrders([{ ...mockOrder, id: 99, symbol: "GOOGL" }]);

    // The new account's orders should appear
    expect(await screen.findByText("GOOGL")).toBeInTheDocument();
  });

  it("does not overwrite orders after account switch when initial loadOrders is slow", async () => {
    const user = userEvent.setup();
    let resolveOrders1!: (value: unknown) => void;
    const orders1Promise = new Promise<typeof mockOrder[]>((resolve) => { resolveOrders1 = resolve; });

    const secondAccount = { id: 2, name: "test2", initial_cash: "100000.00", status: "active", base_currency: "CNY" };
    listAccountsMock.mockResolvedValue([mockAccount, secondAccount]);
    // Account 1's orders are deferred
    listOrdersMock.mockReturnValueOnce(orders1Promise);
    // Account 2's orders will resolve immediately
    listOrdersMock.mockImplementation((accountId: number) => {
      if (accountId === 2) return Promise.resolve([{ ...mockOrder, id: 99, symbol: "GOOGL" }]);
      return Promise.resolve([]);
    });

    render(<OrdersPage />);

    // Account 1 auto-selected, orders still loading (deferred)
    expect(await screen.findByText("Orders")).toBeInTheDocument();

    // Switch to Account 2 while Account 1's orders are in flight
    await user.selectOptions(screen.getByLabelText("Account"), "2");

    // Account 2's GOOGL orders should appear
    expect(await screen.findByText("GOOGL")).toBeInTheDocument();

    // Now resolve Account 1's deferred orders — the stale response should be discarded
    await act(async () => {
      resolveOrders1([mockOrder]); // AAPL
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    // Account 2 data must remain; AAPL must not reappear
    expect(screen.getByText("GOOGL")).toBeInTheDocument();
    expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
  });

  it("hides loading panel after successful initial load", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue([mockOrder]);

    render(<OrdersPage />);

    // Loading should be visible initially
    expect(screen.getByText("Loading orders...")).toBeInTheDocument();

    // After data loads, loading should disappear and orders should render
    expect(await screen.findByText("AAPL")).toBeInTheDocument();
    expect(screen.queryByText("Loading orders...")).not.toBeInTheDocument();
  });

  it("does not overwrite orders with stale cancel refresh after account switch", async () => {
    const user = userEvent.setup();
    let resolveCancel!: (value: unknown) => void;
    const cancelPromise = new Promise<typeof mockOrder>((resolve) => { resolveCancel = resolve; });

    const secondAccount = { id: 2, name: "test2", initial_cash: "100000.00", status: "active", base_currency: "CNY" };
    listAccountsMock.mockResolvedValue([mockAccount, secondAccount]);
    // Return different orders per account so a stale refresh is detectable
    listOrdersMock.mockImplementation((accountId: number) => {
      if (accountId === 2) return Promise.resolve([{ ...mockOrder, id: 99, symbol: "GOOGL" }]);
      return Promise.resolve([mockOrder]); // AAPL for Account 1
    });
    cancelOrderMock.mockReturnValue(cancelPromise);

    render(<OrdersPage />);
    expect(await screen.findByText("AAPL")).toBeInTheDocument();
    expect(screen.queryByText("GOOGL")).not.toBeInTheDocument();

    // Click Cancel (hangs on deferred promise)
    await user.click(screen.getByText("Cancel"));
    expect(cancelOrderMock).toHaveBeenCalledWith(42);

    // Switch to Account 2 while cancel is in flight
    await user.selectOptions(screen.getByLabelText("Account"), "2");

    // Account 2 data should render
    expect(await screen.findByText("GOOGL")).toBeInTheDocument();
    expect(screen.queryByText("AAPL")).not.toBeInTheDocument();

    // Now resolve the cancel — its stale refresh would call loadOrders(1) which returns AAPL.
    // Without the fix AAPL would reappear, overwriting GOOGL.
    await act(async () => {
      resolveCancel({ ...mockOrder, status: "cancelled" });
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    // Account 2 data must remain; AAPL must not reappear
    expect(screen.getByText("GOOGL")).toBeInTheDocument();
    expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
  });
});
