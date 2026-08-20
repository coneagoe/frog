import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { listAccounts, listTrades } from "@/lib/api-client";
import type { Account, Trade, TradePage } from "@/lib/types";
import { TradesPage } from "./trades-page";

const mockSearchParams = vi.hoisted(() => new URLSearchParams());
const mockRouterReplace = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({
  useSearchParams: () => mockSearchParams,
  useRouter: () => ({ replace: mockRouterReplace }),
}));

vi.mock("@/lib/api-client", () => ({
  listAccounts: vi.fn(),
  listTrades: vi.fn(),
}));

const listAccountsMock = vi.mocked(listAccounts);
const listTradesMock = vi.mocked(listTrades);

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
  cumulative_withdrawal: "0.00",
};
const secondAccount: Account = { ...mockAccount, id: 2, name: "test2" };
const mockTrade: Trade = {
  id: 42,
  order_id: 1,
  account_id: 1,
  symbol: "AAPL",
  stock_name: "Apple",
  side: "buy",
  quantity: 100,
  price: "150.00",
  amount: "15000.00",
  fees: "15.00",
  trade_date: "2026-06-27",
  comment: null,
};

function makeTradePage(
  items: Trade[],
  overrides: Partial<TradePage> = {},
): TradePage {
  return {
    items,
    page: 1,
    page_size: 25,
    total_count: items.length,
    total_pages: items.length > 0 ? 1 : 0,
    ...overrides,
  };
}

function mockTradesEchoingPage(
  totalPages: number,
  totalCount: number,
  items: Trade[] = [mockTrade],
) {
  listTradesMock.mockImplementation((accountId, params) =>
    Promise.resolve(
      makeTradePage(items, {
        page: params?.page ?? 1,
        total_pages: totalPages,
        total_count: totalCount,
      }),
    ),
  );
}

function expectedShanghaiToday(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function expectedShiftDate(date: string, days: number): string {
  const [year, month, day] = date.split("-").map(Number);
  const shifted = new Date(Date.UTC(year, month - 1, day + days));
  return `${shifted.getUTCFullYear()}-${String(shifted.getUTCMonth() + 1).padStart(2, "0")}-${String(shifted.getUTCDate()).padStart(2, "0")}`;
}

describe("TradesPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    for (const key of [...mockSearchParams.keys()])
      mockSearchParams.delete(key);
  });

  it("loads the first account, default trailing 30-day range, and renders a trade row", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listTradesMock.mockResolvedValue(makeTradePage([mockTrade]));
    render(<TradesPage />);
    expect(await screen.findByText("AAPL")).toBeInTheDocument();
    const today = expectedShanghaiToday();
    expect(listTradesMock).toHaveBeenCalledWith(1, {
      start_date: expectedShiftDate(today, -29),
      end_date: today,
      page: 1,
      page_size: 25,
    });
    expect(
      screen.getByRole("button", { name: "Last 30 days" }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("renders trade comments and remains read-only", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listTradesMock.mockResolvedValue(
      makeTradePage([{ ...mockTrade, comment: "trade rationale" }]),
    );
    render(<TradesPage />);
    expect(await screen.findByText("trade rationale")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Cancel" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Edit" }),
    ).not.toBeInTheDocument();
  });

  it("renders a dash for null and empty trade comments", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listTradesMock.mockResolvedValue(
      makeTradePage([mockTrade, { ...mockTrade, id: 43, comment: "" }]),
    );
    render(<TradesPage />);
    expect(await screen.findByText("Comment")).toBeInTheDocument();
    expect(screen.getAllByText("-")).toHaveLength(2);
  });

  it("restores account, explicit dates, and page from the URL", async () => {
    mockSearchParams.set("accountId", "2");
    mockSearchParams.set("start_date", "2026-06-01");
    mockSearchParams.set("end_date", "2026-06-15");
    mockSearchParams.set("page", "3");
    listAccountsMock.mockResolvedValue([mockAccount, secondAccount]);
    listTradesMock.mockResolvedValue(
      makeTradePage([mockTrade], { page: 3, total_pages: 3, total_count: 60 }),
    );
    render(<TradesPage />);
    expect(await screen.findByText("AAPL")).toBeInTheDocument();
    expect(listTradesMock).toHaveBeenCalledWith(2, {
      start_date: "2026-06-01",
      end_date: "2026-06-15",
      page: 3,
      page_size: 25,
    });
    expect(screen.getByLabelText("Account")).toHaveValue("2");
    expect(screen.getByLabelText("Start date")).toHaveValue("2026-06-01");
    expect(screen.getByLabelText("End date")).toHaveValue("2026-06-15");
    await waitFor(() =>
      expect(mockRouterReplace).toHaveBeenCalledWith(
        "/trades?accountId=2&start_date=2026-06-01&end_date=2026-06-15&page=3",
      ),
    );
  });

  it("applies Shanghai Today, 7-day, and 30-day presets", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    mockTradesEchoingPage(2, 30);
    render(<TradesPage />);
    await screen.findByText("AAPL");
    const today = expectedShanghaiToday();
    await userEvent.click(screen.getByRole("button", { name: "Today" }));
    await waitFor(() =>
      expect(listTradesMock).toHaveBeenCalledWith(1, {
        start_date: today,
        end_date: today,
        page: 1,
        page_size: 25,
      }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Last 7 days" }));
    await waitFor(() =>
      expect(listTradesMock).toHaveBeenCalledWith(1, {
        start_date: expectedShiftDate(today, -6),
        end_date: today,
        page: 1,
        page_size: 25,
      }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Last 30 days" }));
    await waitFor(() =>
      expect(listTradesMock).toHaveBeenCalledWith(1, {
        start_date: expectedShiftDate(today, -29),
        end_date: today,
        page: 1,
        page_size: 25,
      }),
    );
  });

  it("applies a custom inclusive range and resets page", async () => {
    mockSearchParams.set("page", "2");
    listAccountsMock.mockResolvedValue([mockAccount]);
    mockTradesEchoingPage(5, 120);
    render(<TradesPage />);
    await screen.findByText(/Page 2 of 5/);
    fireEvent.change(screen.getByLabelText("Start date"), {
      target: { value: "2026-05-01" },
    });
    fireEvent.change(screen.getByLabelText("End date"), {
      target: { value: "2026-05-31" },
    });
    await waitFor(() =>
      expect(listTradesMock).toHaveBeenCalledWith(1, {
        start_date: "2026-05-01",
        end_date: "2026-05-31",
        page: 1,
        page_size: 25,
      }),
    );
    expect(mockRouterReplace).toHaveBeenCalledWith(
      "/trades?accountId=1&start_date=2026-05-01&end_date=2026-05-31&page=1",
    );
  });

  it("shows invalid range feedback and sends no request", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listTradesMock.mockResolvedValue(makeTradePage([mockTrade]));
    render(<TradesPage />);
    await screen.findByText("AAPL");
    const callsBefore = listTradesMock.mock.calls.length;
    fireEvent.change(screen.getByLabelText("Start date"), {
      target: { value: "2099-01-10" },
    });
    fireEvent.change(screen.getByLabelText("End date"), {
      target: { value: "2099-01-01" },
    });
    expect(
      await screen.findByText("Start date must be on or before end date."),
    ).toBeInTheDocument();
    expect(listTradesMock.mock.calls.length).toBe(callsBefore);
  });

  it("resets page when the account changes and discards stale responses", async () => {
    mockSearchParams.set("page", "2");
    let resolveFirst!: (value: TradePage) => void;
    const firstRequest = new Promise<TradePage>((resolve) => {
      resolveFirst = resolve;
    });
    listAccountsMock.mockResolvedValue([mockAccount, secondAccount]);
    listTradesMock.mockReturnValueOnce(firstRequest);
    listTradesMock.mockImplementation((accountId, params) =>
      Promise.resolve(
        makeTradePage([{ ...mockTrade, symbol: "GOOGL" }], {
          page: params?.page ?? 1,
          total_pages: 3,
          total_count: 61,
        }),
      ),
    );
    render(<TradesPage />);
    await waitFor(() => expect(listTradesMock).toHaveBeenCalledTimes(1));
    await userEvent.selectOptions(screen.getByLabelText("Account"), "2");
    expect(await screen.findByText("GOOGL")).toBeInTheDocument();
    expect(listTradesMock).toHaveBeenCalledWith(
      2,
      expect.objectContaining({ page: 1, page_size: 25 }),
    );
    await act(async () => {
      resolveFirst(makeTradePage([mockTrade]));
    });
    expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
  });

  it("paginates with Next and Previous while syncing the URL", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    mockTradesEchoingPage(3, 61);
    render(<TradesPage />);
    expect(await screen.findByText(/Page 1 of 3/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText(/Page 2 of 3/)).toBeInTheDocument();
    expect(mockRouterReplace).toHaveBeenCalledWith(
      expect.stringMatching(/[?&]page=2(&|$)/),
    );
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(await screen.findByText(/Page 1 of 3/)).toBeInTheDocument();
  });

  it("shows loading, empty-account, error, and filtered-empty states", async () => {
    listAccountsMock.mockResolvedValue([]);
    render(<TradesPage />);
    expect(
      await screen.findByText(/No paper accounts yet/),
    ).toBeInTheDocument();

    listAccountsMock.mockResolvedValue([mockAccount]);
    listTradesMock.mockResolvedValue(
      makeTradePage([], { total_count: 0, total_pages: 0 }),
    );
    render(<TradesPage />);
    expect(await screen.findByText("No trades")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Next" }),
    ).not.toBeInTheDocument();
  });

  it("shows loading while accounts are pending", () => {
    listAccountsMock.mockReturnValue(new Promise(() => {}));
    render(<TradesPage />);
    expect(screen.getByText("Loading trades...")).toBeInTheDocument();
  });

  it("shows an API error", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listTradesMock.mockRejectedValue(
      new Error("Failed to load historical trades"),
    );
    render(<TradesPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Failed to load historical trades",
    );
  });
});
