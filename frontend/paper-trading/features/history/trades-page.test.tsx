import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { listAccounts, listTrades } from "@/lib/api-client";
import { TradesPage } from "./trades-page";

const mockSearchParams = vi.hoisted(() => new URLSearchParams());
vi.mock("next/navigation", () => ({
  useSearchParams: () => mockSearchParams
}));

vi.mock("@/lib/api-client", () => ({
  listAccounts: vi.fn(),
  listTrades: vi.fn()
}));

const listAccountsMock = vi.mocked(listAccounts);
const listTradesMock = vi.mocked(listTrades);

const mockAccount = { id: 1, name: "demo", initial_cash: "100000.00", status: "active", base_currency: "CNY" };
const mockTrade = {
  id: 42,
  order_id: 1,
  account_id: 1,
  symbol: "AAPL",
  side: "buy" as const,
  quantity: 100,
  price: "150.00",
  amount: "15000.00",
  fees: "15.00",
  trade_date: "2026-06-27",
  comment: null
};

describe("TradesPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("loads the first account, fetches trades, and renders a trade row", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listTradesMock.mockResolvedValue([mockTrade]);

    render(<TradesPage />);

    expect(await screen.findByText("Trades")).toBeInTheDocument();
    expect(await screen.findByText("AAPL")).toBeInTheDocument();
    // listAccounts must be called at least once
    expect(listAccountsMock.mock.calls.length).toBeGreaterThanOrEqual(1);
    // listTrades must be called with the first account id explicitly
    expect(listTradesMock).toHaveBeenCalledWith(1);
  });

  it("renders comment column with dash for null", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listTradesMock.mockResolvedValue([mockTrade]);

    render(<TradesPage />);

    expect(await screen.findByText("Comment")).toBeInTheDocument();
    expect(screen.getByText("-")).toBeInTheDocument();
  });

  it("renders comment text when non-null", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listTradesMock.mockResolvedValue([{ ...mockTrade, comment: "trade rationale" }]);

    render(<TradesPage />);

    expect(await screen.findByText("trade rationale")).toBeInTheDocument();
  });

  it("renders dash when trade comment is an empty string", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listTradesMock.mockResolvedValue([{ ...mockTrade, comment: "" }]);

    render(<TradesPage />);

    expect(await screen.findByText("-")).toBeInTheDocument();
  });

  it("renders muted copy about review of historical paper executions", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listTradesMock.mockResolvedValue([mockTrade]);

    render(<TradesPage />);

    expect(await screen.findByText("Review historical paper executions.")).toBeInTheDocument();
  });

  it("has no Cancel button (read-only)", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listTradesMock.mockResolvedValue([mockTrade]);

    render(<TradesPage />);

    expect(await screen.findByText("AAPL")).toBeInTheDocument();
    expect(screen.queryByText("Cancel")).not.toBeInTheDocument();
  });

  it("shows ErrorBanner when loading trades fails", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listTradesMock.mockRejectedValue(new Error("Failed to load historical trades"));

    render(<TradesPage />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Failed to load historical trades");
    }, { timeout: 5000 });
  });

  it("clears trades before fetching a different account", async () => {
    const user = userEvent.setup();
    let resolveTrades!: (value: unknown) => void;
    const tradesPromise = new Promise<typeof mockTrade[]>((resolve) => { resolveTrades = resolve; });

    const secondAccount = { id: 2, name: "test2", initial_cash: "100000.00", status: "active", base_currency: "CNY" };
    listAccountsMock.mockResolvedValue([mockAccount, secondAccount]);
    listTradesMock.mockResolvedValue([mockTrade]);

    render(<TradesPage />);
    expect(await screen.findByText("AAPL")).toBeInTheDocument();

    // Defer Account 2's trade fetch so we can observe the cleared state
    listTradesMock.mockReturnValue(tradesPromise);

    // Switch to Account 2 — trades should clear before the deferred fetch completes
    await user.selectOptions(screen.getByLabelText("Account"), "2");

    // listTrades must be called with the second account explicitly
    expect(listTradesMock).toHaveBeenCalledWith(2);

    // Old trades should be gone even though the new fetch hasn't resolved
    await waitFor(() => {
      expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
    });

    // Now let the deferred fetch resolve with new trades
    resolveTrades([{ ...mockTrade, id: 99, symbol: "GOOGL" }]);

    // The new account's trades should appear
    expect(await screen.findByText("GOOGL")).toBeInTheDocument();
  });

  it("does not overwrite trades after account switch when initial loadTrades is slow", async () => {
    const user = userEvent.setup();
    let resolveTrades1!: (value: unknown) => void;
    const trades1Promise = new Promise<typeof mockTrade[]>((resolve) => { resolveTrades1 = resolve; });

    const secondAccount = { id: 2, name: "test2", initial_cash: "100000.00", status: "active", base_currency: "CNY" };
    listAccountsMock.mockResolvedValue([mockAccount, secondAccount]);
    // Account 1's trades are deferred
    listTradesMock.mockReturnValueOnce(trades1Promise);
    // Account 2's trades will resolve immediately
    listTradesMock.mockImplementation((accountId: number) => {
      if (accountId === 2) return Promise.resolve([{ ...mockTrade, id: 99, symbol: "GOOGL" }]);
      return Promise.resolve([]);
    });

    render(<TradesPage />);

    // Account 1 auto-selected, trades still loading (deferred)
    expect(await screen.findByText("Trades")).toBeInTheDocument();

    // Switch to Account 2 while Account 1's trades are in flight
    await user.selectOptions(screen.getByLabelText("Account"), "2");

    // Account 2's GOOGL trades should appear
    expect(await screen.findByText("GOOGL")).toBeInTheDocument();

    // Now resolve Account 1's deferred trades — the stale response should be discarded
    await act(async () => {
      resolveTrades1([mockTrade]); // AAPL
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    // Account 2 data must remain; AAPL must not reappear
    expect(screen.getByText("GOOGL")).toBeInTheDocument();
    expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
  });

  it("does not overwrite trades with stale data after fast account switch", async () => {
    const user = userEvent.setup();

    const secondAccount = { id: 2, name: "test2", initial_cash: "100000.00", status: "active", base_currency: "CNY" };
    listAccountsMock.mockResolvedValue([mockAccount, secondAccount]);
    // Return different trades per account so a stale refresh is detectable
    listTradesMock.mockImplementation((accountId: number) => {
      if (accountId === 2) return Promise.resolve([{ ...mockTrade, id: 99, symbol: "GOOGL" }]);
      return Promise.resolve([mockTrade]); // AAPL for Account 1
    });

    render(<TradesPage />);
    expect(await screen.findByText("AAPL")).toBeInTheDocument();
    expect(screen.queryByText("GOOGL")).not.toBeInTheDocument();

    // Switch to Account 2
    await user.selectOptions(screen.getByLabelText("Account"), "2");

    // listTrades must be called with the second account explicitly
    expect(listTradesMock).toHaveBeenCalledWith(2);

    // Account 2 data should render
    expect(await screen.findByText("GOOGL")).toBeInTheDocument();
    expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
  });

  it("hides loading panel after successful initial load", async () => {
    listAccountsMock.mockResolvedValue([mockAccount]);
    listTradesMock.mockResolvedValue([mockTrade]);

    render(<TradesPage />);

    // Loading should be visible initially
    expect(screen.getByText("Loading trades...")).toBeInTheDocument();

    // After data loads, loading should disappear and trades should render
    expect(await screen.findByText("AAPL")).toBeInTheDocument();
    expect(screen.queryByText("Loading trades...")).not.toBeInTheDocument();
  });

  it("shows loading state while accounts are being loaded", async () => {
    let resolveAccounts!: (value: unknown) => void;
    const accountsPromise = new Promise<typeof mockAccount[]>((resolve) => { resolveAccounts = resolve; });

    listAccountsMock.mockReturnValue(accountsPromise);
    listTradesMock.mockResolvedValue([mockTrade]);

    render(<TradesPage />);

    expect(screen.getByText("Loading trades...")).toBeInTheDocument();

    resolveAccounts([mockAccount]);

    expect(await screen.findByText("Trades")).toBeInTheDocument();
  });

  it("shows empty account state when no accounts exist", async () => {
    listAccountsMock.mockResolvedValue([]);

    render(<TradesPage />);

    expect(await screen.findByText(/No paper accounts yet/)).toBeInTheDocument();
  });
});
