import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cancelOrder, deleteOrder, listAccounts, listOrders, updateOrderComment } from "@/lib/api-client";
import type { Account, Order, OrderPage } from "@/lib/types";
import { OrdersPage, presetRange, shanghaiToday, shiftDate } from "./orders-page";

const mockSearchParams = vi.hoisted(() => new URLSearchParams());
const mockRouterReplace = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({
  useSearchParams: () => mockSearchParams,
  useRouter: () => ({ replace: mockRouterReplace })
}));

vi.mock("@/lib/api-client", () => ({
  listAccounts: vi.fn(),
  listOrders: vi.fn(),
  cancelOrder: vi.fn(),
  deleteOrder: vi.fn(),
  updateOrderComment: vi.fn()
}));

const listAccountsMock = vi.mocked(listAccounts);
const listOrdersMock = vi.mocked(listOrders);
const cancelOrderMock = vi.mocked(cancelOrder);
const deleteOrderMock = vi.mocked(deleteOrder);
const updateOrderCommentMock = vi.mocked(updateOrderComment);

const mockAccount: Account = {
  id: 1,
  name: "demo",
  initial_cash: "100000.00",
  cash_available: "100000.00",
  status: "active",
  base_currency: "CNY",
  fee_preset: "standard",
  commission_rate: "0.0003",
  min_commission: "5.00",
  stamp_duty_rate: "0.001",
  transfer_fee_rate: "0.00002",
  share_count: "1000",
  net_asset_value: "100.00",
  cumulative_deposit: "0.00",
  cumulative_withdrawal: "0.00"
};
const secondAccount: Account = { ...mockAccount, id: 2, name: "test2" };

const mockOrder: Order = {
  id: 42,
  account_id: 1,
  symbol: "AAPL",
  stock_name: "Apple",
  side: "buy" as const,
  quantity: 100,
  limit_price: "150.00",
  trade_date: "2026-06-27",
  status: "accepted",
  filled_quantity: 0,
  frozen_cash: "15000.00",
  frozen_quantity: 100,
  rejection_code: null,
  rejection_reason: null,
  comment: null
};

function makeOrderPage(items: Order[], overrides: Partial<OrderPage> = {}): OrderPage {
  return {
    items,
    page: 1,
    page_size: 25,
    total_count: items.length,
    total_pages: items.length > 0 ? 1 : 0,
    ...overrides
  };
}

function mockOrdersEchoingPage(totalPages: number, totalCount: number, items: Order[] = [mockOrder]) {
  listOrdersMock.mockImplementation((accountId, params) => {
    const requestedPage = params?.page ?? 1;
    return Promise.resolve(makeOrderPage(items, { page: requestedPage, total_pages: totalPages, total_count: totalCount }));
  });
}

// Independent re-implementations so the page tests stay meaningful regardless of runtime clock.
function expectedShanghaiToday(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).format(new Date());
}

function expectedShiftDate(date: string, days: number): string {
  const [year, month, day] = date.split("-").map(Number);
  const shifted = new Date(Date.UTC(year, month - 1, day + days));
  const yyyy = shifted.getUTCFullYear();
  const mm = String(shifted.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(shifted.getUTCDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

describe("OrdersPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    for (const key of [...mockSearchParams.keys()]) {
      mockSearchParams.delete(key);
    }
  });

  it("loads the first account, fetches orders, and renders an order row", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue(makeOrderPage([mockOrder]));

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
    listOrdersMock.mockResolvedValue(makeOrderPage([mockOrder]));
    cancelOrderMock.mockResolvedValue({ ...mockOrder, status: "cancelled" });

    render(<OrdersPage />);

    expect(await screen.findByText("Cancel")).toBeInTheDocument();
    await user.click(screen.getByText("Cancel"));

    expect(cancelOrderMock).toHaveBeenCalledWith(42);
  });

  it("refreshes listOrders after cancellation", async () => {
    const user = userEvent.setup();
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue(makeOrderPage([mockOrder]));
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
    listOrdersMock.mockResolvedValue(makeOrderPage([mockOrder]));
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
    let resolveOrders!: (value: OrderPage) => void;
    const ordersPromise = new Promise<OrderPage>((resolve) => { resolveOrders = resolve; });

    listAccountsMock.mockResolvedValue([mockAccount, secondAccount]);
    listOrdersMock.mockResolvedValue(makeOrderPage([mockOrder]));

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
    resolveOrders(makeOrderPage([{ ...mockOrder, id: 99, symbol: "GOOGL" }]));

    // The new account's orders should appear
    expect(await screen.findByText("GOOGL")).toBeInTheDocument();
  });

  it("does not overwrite orders after account switch when initial loadOrders is slow", async () => {
    const user = userEvent.setup();
    let resolveOrders1!: (value: OrderPage) => void;
    const orders1Promise = new Promise<OrderPage>((resolve) => { resolveOrders1 = resolve; });

    listAccountsMock.mockResolvedValue([mockAccount, secondAccount]);
    // Account 1's orders are deferred
    listOrdersMock.mockReturnValueOnce(orders1Promise);
    // Account 2's orders will resolve immediately
    listOrdersMock.mockImplementation((accountId: number) => {
      if (accountId === 2) return Promise.resolve(makeOrderPage([{ ...mockOrder, id: 99, symbol: "GOOGL" }]));
      return Promise.resolve(makeOrderPage([]));
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
      resolveOrders1(makeOrderPage([mockOrder])); // AAPL
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    // Account 2 data must remain; AAPL must not reappear
    expect(screen.getByText("GOOGL")).toBeInTheDocument();
    expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
  });

  it("hides loading panel after successful initial load", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue(makeOrderPage([mockOrder]));

    render(<OrdersPage />);

    // Loading should be visible initially
    expect(screen.getByText("Loading orders...")).toBeInTheDocument();

    // After data loads, loading should disappear and orders should render
    expect(await screen.findByText("AAPL")).toBeInTheDocument();
    expect(screen.queryByText("Loading orders...")).not.toBeInTheDocument();
  });

  it("renders comment column with dash for null", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue(makeOrderPage([mockOrder]));

    render(<OrdersPage />);

    expect(await screen.findByText("Comment")).toBeInTheDocument();
    expect(screen.getByText("-")).toBeInTheDocument();
  });

  it("renders comment text when non-null", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue(makeOrderPage([{ ...mockOrder, comment: "my rationale" }]));

    render(<OrdersPage />);

    expect(await screen.findByText("my rationale")).toBeInTheDocument();
  });

  it("renders dash when order comment is an empty string", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue(makeOrderPage([{ ...mockOrder, comment: "" }]));

    render(<OrdersPage />);

    expect(await screen.findByText("-")).toBeInTheDocument();
  });

  it("shows Edit button on orders", async () => {
    const user = userEvent.setup();
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue(makeOrderPage([mockOrder]));

    render(<OrdersPage />);

    expect(await screen.findByText("Edit")).toBeInTheDocument();
    await user.click(screen.getByText("Edit"));
    expect(screen.getByDisplayValue("")).toBeInTheDocument();
  });

  it("shows inline edit controls and saves comment", async () => {
    const user = userEvent.setup();
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue(makeOrderPage([{ ...mockOrder, comment: "old comment" }]));
    updateOrderCommentMock.mockResolvedValue({ ...mockOrder, id: 42, comment: "updated comment" });

    render(<OrdersPage />);

    expect(await screen.findByText("old comment")).toBeInTheDocument();
    await user.click(screen.getByText("Edit"));

    const input = screen.getByDisplayValue("old comment");
    await user.clear(input);
    await user.type(input, "updated comment");
    await user.click(screen.getByText("Save"));

    expect(updateOrderCommentMock).toHaveBeenCalledWith(42, "updated comment");
    expect(await screen.findByText("updated comment")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  });

  it("cancels inline edit without saving", async () => {
    const user = userEvent.setup();
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue(makeOrderPage([{ ...mockOrder, comment: "original" }]));

    render(<OrdersPage />);

    expect(await screen.findByText("original")).toBeInTheDocument();
    await user.click(screen.getByText("Edit"));

    const input = screen.getByDisplayValue("original");
    await user.clear(input);
    await user.type(input, "changed but cancelled");
    await user.click(screen.getByText("Cancel"));

    expect(updateOrderCommentMock).not.toHaveBeenCalled();
    expect(screen.getByText("original")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  });

  it("clears comment to dash when saving empty string", async () => {
    const user = userEvent.setup();
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue(makeOrderPage([{ ...mockOrder, comment: "to clear" }]));
    updateOrderCommentMock.mockResolvedValue({ ...mockOrder, id: 42, comment: null });

    render(<OrdersPage />);

    expect(await screen.findByText("to clear")).toBeInTheDocument();
    await user.click(screen.getByText("Edit"));

    const input = screen.getByDisplayValue("to clear");
    await user.clear(input);
    await user.click(screen.getByText("Save"));

    expect(updateOrderCommentMock).toHaveBeenCalledWith(42, "");
    expect(await screen.findByText("-")).toBeInTheDocument();
  });

  it("shows ErrorBanner when updateOrderComment fails", async () => {
    const user = userEvent.setup();
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue(makeOrderPage([{ ...mockOrder, comment: "original" }]));
    updateOrderCommentMock.mockRejectedValue(new Error("order not found"));

    render(<OrdersPage />);

    expect(await screen.findByText("original")).toBeInTheDocument();
    await user.click(screen.getByText("Edit"));

    const input = screen.getByDisplayValue("original");
    await user.clear(input);
    await user.type(input, "new value");
    await user.click(screen.getByText("Save"));

    await screen.findByRole("alert");
    expect(screen.getByRole("alert")).toHaveTextContent("order not found");
    // Should remain in edit mode on error
    expect(screen.getByDisplayValue("new value")).toBeInTheDocument();
    expect(screen.getByText("Cancel")).toBeInTheDocument();
  });

  it("does not delete an order when confirmation is cancelled", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue(makeOrderPage([mockOrder]));

    render(<OrdersPage />);

    await screen.findByText("AAPL");
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(deleteOrderMock).not.toHaveBeenCalled();
  });

  it("shows the exact confirmation message when deleting an order", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue(makeOrderPage([mockOrder]));

    render(<OrdersPage />);

    await screen.findByText("AAPL");
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(confirmSpy).toHaveBeenCalledWith(
      "Delete this order? Filled trades, cash ledger, positions, and snapshots for this paper account will be recalculated."
    );
  });

  it("deletes an order and reloads orders after confirmation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue(makeOrderPage([mockOrder]));
    deleteOrderMock.mockResolvedValue(undefined);

    render(<OrdersPage />);

    await screen.findByText("AAPL");
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(deleteOrderMock).toHaveBeenCalledWith(42);
    await waitFor(() => expect(listOrdersMock).toHaveBeenCalledTimes(2));
  });

  it("shows an error when deleting an order fails", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue(makeOrderPage([mockOrder]));
    deleteOrderMock.mockRejectedValue(new Error("Failed to delete order"));

    render(<OrdersPage />);

    await screen.findByText("AAPL");
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Failed to delete order");
  });

  it("does not overwrite orders with stale cancel refresh after account switch", async () => {
    const user = userEvent.setup();
    let resolveCancel!: (value: Order) => void;
    const cancelPromise = new Promise<Order>((resolve) => { resolveCancel = resolve; });

    listAccountsMock.mockResolvedValue([mockAccount, secondAccount]);
    // Return different orders per account so a stale refresh is detectable
    listOrdersMock.mockImplementation((accountId: number) => {
      if (accountId === 2) return Promise.resolve(makeOrderPage([{ ...mockOrder, id: 99, symbol: "GOOGL" }]));
      return Promise.resolve(makeOrderPage([mockOrder])); // AAPL for Account 1
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

  it("restores account, explicit dates, and page from the URL", async () => {
    mockSearchParams.set("accountId", "2");
    mockSearchParams.set("start_date", "2026-06-01");
    mockSearchParams.set("end_date", "2026-06-15");
    mockSearchParams.set("page", "3");
    listAccountsMock.mockResolvedValue([mockAccount, secondAccount]);
    listOrdersMock.mockResolvedValue(makeOrderPage([mockOrder], { page: 3, total_pages: 3, total_count: 60 }));

    render(<OrdersPage />);

    expect(await screen.findByText("AAPL")).toBeInTheDocument();
    expect(listOrdersMock).toHaveBeenCalledWith(2, {
      start_date: "2026-06-01",
      end_date: "2026-06-15",
      page: 3,
      page_size: 25
    });
    expect(screen.getByLabelText("Account")).toHaveValue("2");
    expect(screen.getByLabelText("Start date")).toHaveValue("2026-06-01");
    expect(screen.getByLabelText("End date")).toHaveValue("2026-06-15");
    expect(await screen.findByText(/Page 3 of 3/)).toBeInTheDocument();
    await waitFor(() => {
      expect(mockRouterReplace).toHaveBeenCalledWith("/orders?accountId=2&start_date=2026-06-01&end_date=2026-06-15&page=3");
    });
  });

  it("defaults to the trailing 30-day range when the URL has no dates", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue(makeOrderPage([mockOrder]));

    render(<OrdersPage />);
    expect(await screen.findByText("AAPL")).toBeInTheDocument();

    const today = expectedShanghaiToday();
    expect(listOrdersMock).toHaveBeenCalledWith(1, {
      start_date: expectedShiftDate(today, -29),
      end_date: today,
      page: 1,
      page_size: 25
    });
    expect(screen.getByRole("button", { name: "Last 30 days" })).toHaveAttribute("aria-pressed", "true");
  });

  it("applies the Today preset with Asia/Shanghai dates and resets the page", async () => {
    mockSearchParams.set("page", "2");
    listAccountsMock.mockResolvedValue([mockAccount]);
    mockOrdersEchoingPage(2, 30);

    render(<OrdersPage />);
    await screen.findByText(/Page 2 of 2/);

    await userEvent.click(screen.getByRole("button", { name: "Today" }));

    const today = expectedShanghaiToday();
    await waitFor(() => {
      expect(listOrdersMock).toHaveBeenCalledWith(1, {
        start_date: today,
        end_date: today,
        page: 1,
        page_size: 25
      });
    });
    expect(screen.getByRole("button", { name: "Today" })).toHaveAttribute("aria-pressed", "true");
    expect(mockRouterReplace).toHaveBeenCalledWith(expect.stringMatching(new RegExp(`[?&]start_date=${today}(&|$)`)));
    expect(mockRouterReplace).toHaveBeenCalledWith(expect.stringMatching(/[?&]page=1(&|$)/));
  });

  it("applies the trailing 7-day preset from today minus 6 days through today", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    mockOrdersEchoingPage(1, 1);

    render(<OrdersPage />);
    await screen.findByText("AAPL");

    await userEvent.click(screen.getByRole("button", { name: "Last 7 days" }));

    const today = expectedShanghaiToday();
    await waitFor(() => {
      expect(listOrdersMock).toHaveBeenCalledWith(1, {
        start_date: expectedShiftDate(today, -6),
        end_date: today,
        page: 1,
        page_size: 25
      });
    });
    expect(screen.getByRole("button", { name: "Last 7 days" })).toHaveAttribute("aria-pressed", "true");
  });

  it("applies the trailing 30-day preset from today minus 29 days through today", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    mockOrdersEchoingPage(1, 1);

    render(<OrdersPage />);
    await screen.findByText("AAPL");

    await userEvent.click(screen.getByRole("button", { name: "Last 30 days" }));

    const today = expectedShanghaiToday();
    await waitFor(() => {
      expect(listOrdersMock).toHaveBeenCalledWith(1, {
        start_date: expectedShiftDate(today, -29),
        end_date: today,
        page: 1,
        page_size: 25
      });
    });
    expect(screen.getByRole("button", { name: "Last 30 days" })).toHaveAttribute("aria-pressed", "true");
  });

  it("applies a custom inclusive date range and resets the page", async () => {
    mockSearchParams.set("page", "2");
    listAccountsMock.mockResolvedValue([mockAccount]);
    mockOrdersEchoingPage(5, 120);

    render(<OrdersPage />);
    await screen.findByText(/Page 2 of 5/);

    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-05-01" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2026-05-31" } });

    await waitFor(() => {
      expect(listOrdersMock).toHaveBeenCalledWith(1, {
        start_date: "2026-05-01",
        end_date: "2026-05-31",
        page: 1,
        page_size: 25
      });
    });
    expect(mockRouterReplace).toHaveBeenCalledWith("/orders?accountId=1&start_date=2026-05-01&end_date=2026-05-31&page=1");
    // A custom range does not match any preset
    expect(screen.getByRole("button", { name: "Today" })).toHaveAttribute("aria-pressed", "false");
  });

  it("shows a validation message and sends no request for an invalid custom range", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue(makeOrderPage([mockOrder]));

    render(<OrdersPage />);
    expect(await screen.findByText("AAPL")).toBeInTheDocument();
    const callsBefore = listOrdersMock.mock.calls.length;

    // Both the intermediate and final states are invalid, so no request may fire.
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2099-01-10" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2099-01-01" } });

    expect(await screen.findByText("Start date must be on or before end date.")).toBeInTheDocument();
    expect(listOrdersMock.mock.calls.length).toBe(callsBefore);
    const replacedUrls = mockRouterReplace.mock.calls.map((call) => String(call[0]));
    expect(replacedUrls.every((url) => !url.includes("2099-01-10"))).toBe(true);
  });

  it("resets to page 1 when the account changes", async () => {
    mockSearchParams.set("page", "2");
    listAccountsMock.mockResolvedValue([mockAccount, secondAccount]);
    mockOrdersEchoingPage(3, 61);

    render(<OrdersPage />);
    await screen.findByText(/Page 2 of 3/);

    await userEvent.selectOptions(screen.getByLabelText("Account"), "2");

    await waitFor(() => {
      expect(listOrdersMock).toHaveBeenCalledWith(2, expect.objectContaining({ page: 1, page_size: 25 }));
    });
    expect(await screen.findByText(/Page 1 of 3/)).toBeInTheDocument();
    expect(mockRouterReplace).toHaveBeenCalledWith(expect.stringMatching(/accountId=2/));
  });

  it("paginates with Next and Previous while syncing the page to the URL", async () => {
    mockSearchParams.set("start_date", "2026-06-01");
    mockSearchParams.set("end_date", "2026-06-30");
    listAccountsMock.mockResolvedValue([mockAccount]);
    mockOrdersEchoingPage(3, 61);

    render(<OrdersPage />);
    expect(await screen.findByText(/Page 1 of 3/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(await screen.findByText(/Page 2 of 3/)).toBeInTheDocument();
    expect(listOrdersMock).toHaveBeenCalledWith(1, {
      start_date: "2026-06-01",
      end_date: "2026-06-30",
      page: 2,
      page_size: 25
    });
    expect(mockRouterReplace).toHaveBeenCalledWith(expect.stringMatching(/[?&]page=2(&|$)/));
    expect(screen.getByRole("button", { name: "Previous" })).toBeEnabled();

    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText(/Page 3 of 3/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(await screen.findByText(/Page 2 of 3/)).toBeInTheDocument();
  });

  it("shows an empty state and hides pagination when no orders match the range", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockResolvedValue(makeOrderPage([], { total_count: 0, total_pages: 0 }));

    render(<OrdersPage />);

    expect(await screen.findByText("No orders")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Next" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Previous" })).not.toBeInTheDocument();
  });

  it("adopts the page returned by the API when the requested page is out of range", async () => {
    mockSearchParams.set("page", "99");
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockImplementation((accountId, params) => {
      const requestedPage = params?.page ?? 1;
      return Promise.resolve(makeOrderPage([mockOrder], { page: Math.min(requestedPage, 2), total_pages: 2, total_count: 30 }));
    });

    render(<OrdersPage />);

    expect(await screen.findByText(/Page 2 of 2/)).toBeInTheDocument();
    expect(listOrdersMock).toHaveBeenCalledWith(1, expect.objectContaining({ page: 99, page_size: 25 }));
    await waitFor(() => {
      expect(listOrdersMock).toHaveBeenCalledWith(1, expect.objectContaining({ page: 2, page_size: 25 }));
    });
    expect(mockRouterReplace).toHaveBeenCalledWith(expect.stringMatching(/[?&]page=2(&|$)/));
  });

  it("opens the preceding valid page when a deletion empties the current page", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mockSearchParams.set("page", "2");
    let deleted = false;
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockImplementation((accountId, params) => {
      const requestedPage = params?.page ?? 1;
      return Promise.resolve(
        deleted
          ? makeOrderPage([mockOrder], { page: 1, total_pages: 1, total_count: 25 })
          : makeOrderPage([mockOrder], { page: requestedPage, total_pages: 2, total_count: 26 })
      );
    });
    deleteOrderMock.mockImplementation(async () => { deleted = true; });

    render(<OrdersPage />);
    expect(await screen.findByText(/Page 2 of 2/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(await screen.findByText(/Page 1 of 1/)).toBeInTheDocument();
    expect(mockRouterReplace).toHaveBeenCalledWith(expect.stringMatching(/[?&]page=1(&|$)/));
  });

  it("ignores a stale response when the date range changes while a request is in flight", async () => {
    let resolveFirst!: (value: OrderPage) => void;
    const firstPromise = new Promise<OrderPage>((resolve) => { resolveFirst = resolve; });
    listAccountsMock.mockResolvedValue([mockAccount]);
    listOrdersMock.mockReturnValueOnce(firstPromise);
    listOrdersMock.mockResolvedValue(makeOrderPage([{ ...mockOrder, id: 99, symbol: "GOOGL" }]));

    render(<OrdersPage />);
    await waitFor(() => expect(listOrdersMock).toHaveBeenCalledTimes(1));

    await userEvent.click(screen.getByRole("button", { name: "Today" }));
    expect(await screen.findByText("GOOGL")).toBeInTheDocument();

    // The in-flight default-range response arrives late and must be discarded.
    await act(async () => {
      resolveFirst(makeOrderPage([mockOrder]));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(screen.getByText("GOOGL")).toBeInTheDocument();
    expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
  });
});

describe("Asia/Shanghai date helpers", () => {
  it("resolves today on the Shanghai calendar even when UTC is still on the previous day", () => {
    vi.useFakeTimers();
    try {
      // 2026-08-20 00:30 in Shanghai but 2026-08-19 in UTC; toISOString-based dates would be wrong here.
      vi.setSystemTime(new Date("2026-08-19T16:30:00Z"));
      expect(shanghaiToday()).toBe("2026-08-20");

      // 2026-08-19 23:30 in Shanghai; both calendars agree on this side of the boundary.
      vi.setSystemTime(new Date("2026-08-19T15:30:00Z"));
      expect(shanghaiToday()).toBe("2026-08-19");
    } finally {
      vi.useRealTimers();
    }
  });

  it("builds today, trailing 7-day, and trailing 30-day ranges", () => {
    vi.useFakeTimers();
    try {
      vi.setSystemTime(new Date("2026-08-19T16:30:00Z"));
      expect(presetRange("today")).toEqual(["2026-08-20", "2026-08-20"]);
      expect(presetRange("7d")).toEqual(["2026-08-14", "2026-08-20"]);
      expect(presetRange("30d")).toEqual(["2026-07-22", "2026-08-20"]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("shifts dates across month and year boundaries", () => {
    expect(shiftDate("2026-08-20", -29)).toBe("2026-07-22");
    expect(shiftDate("2026-03-01", -1)).toBe("2026-02-28");
    expect(shiftDate("2026-01-01", -1)).toBe("2025-12-31");
    expect(shiftDate("2026-02-28", 1)).toBe("2026-03-01");
  });
});
