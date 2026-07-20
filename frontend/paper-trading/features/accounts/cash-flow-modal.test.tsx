import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { depositCash, withdrawCash } from "@/lib/api-client";
import { CashFlowModal } from "./cash-flow-modal";

const depositCashMock = vi.mocked(depositCash);
const withdrawCashMock = vi.mocked(withdrawCash);

vi.mock("@/lib/api-client", () => ({
  depositCash: vi.fn(),
  withdrawCash: vi.fn()
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
  transfer_fee_rate: "0.000010",
  share_count: "100000.000000",
  net_asset_value: "1.000000",
  cumulative_deposit: "100000.0000",
  cumulative_withdrawal: "0.0000"
};

describe("CashFlowModal", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("returns null when closed", () => {
    const { container } = render(
      <CashFlowModal account={demoAccount} cashAvailable="100000.0000" mode="deposit" open={false} onClose={vi.fn()} onCompleted={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows deposit dialog with account context", () => {
    render(<CashFlowModal account={demoAccount} cashAvailable="100000.0000" mode="deposit" open onClose={vi.fn()} onCompleted={vi.fn()} />);

    expect(screen.getByRole("dialog", { name: "Deposit cash for demo" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Deposit cash for demo" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Deposit" })).toBeInTheDocument();
  });

  it("shows withdraw dialog with available cash info", () => {
    render(<CashFlowModal account={demoAccount} cashAvailable="50000.0000" mode="withdraw" open onClose={vi.fn()} onCompleted={vi.fn()} />);

    expect(screen.getByRole("dialog", { name: "Withdraw cash from demo" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Withdraw cash from demo" })).toBeInTheDocument();
    expect(screen.getByText("Maximum withdrawable: 50000.0000")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Withdraw" })).toBeInTheDocument();
  });

  it("submits a deposit", async () => {
    depositCashMock.mockResolvedValue({
      account_id: 1,
      cash_available: "110000.0000",
      net_asset_value: "1.000000",
      share_count: "110000.000000",
      ledger: { id: 2, account_id: 1, event_type: "deposit", amount: "10000.0000", note: "add", trade_date: "2026-07-20", net_asset_value: null, share_delta: null }
    });

    render(<CashFlowModal account={demoAccount} cashAvailable="100000.0000" mode="deposit" open onClose={vi.fn()} onCompleted={vi.fn()} />);

    await userEvent.type(screen.getByLabelText("Amount"), "10000");
    await userEvent.clear(screen.getByLabelText("Trade date"));
    await userEvent.type(screen.getByLabelText("Trade date"), "2026-07-20");
    await userEvent.type(screen.getByLabelText("Note"), "add");
    await userEvent.click(screen.getByRole("button", { name: "Deposit" }));

    expect(depositCashMock).toHaveBeenCalledWith(1, { amount: "10000", trade_date: "2026-07-20", note: "add" });
  });

  it("blocks withdrawal above available cash", async () => {
    render(<CashFlowModal account={demoAccount} cashAvailable="1000.0000" mode="withdraw" open onClose={vi.fn()} onCompleted={vi.fn()} />);

    await userEvent.type(screen.getByLabelText("Amount"), "1001");
    await userEvent.click(screen.getByRole("button", { name: "Withdraw" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Amount cannot exceed available cash 1000.0000");
    expect(withdrawCashMock).not.toHaveBeenCalled();
  });

  it("blocks zero and negative amounts", async () => {
    render(<CashFlowModal account={demoAccount} cashAvailable="100000.0000" mode="deposit" open onClose={vi.fn()} onCompleted={vi.fn()} />);

    await userEvent.type(screen.getByLabelText("Amount"), "0");
    await userEvent.click(screen.getByRole("button", { name: "Deposit" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Amount must be greater than 0");
    expect(depositCashMock).not.toHaveBeenCalled();
  });

  it("calls onCompleted and closes on success", async () => {
    const result = {
      account_id: 1,
      cash_available: "110000.0000",
      net_asset_value: "1.000000",
      share_count: "110000.000000",
      ledger: { id: 2, account_id: 1, event_type: "deposit", amount: "10000.0000", note: "add", trade_date: "2026-07-20", net_asset_value: null, share_delta: null }
    };
    depositCashMock.mockResolvedValue(result);
    const onCompleted = vi.fn();
    const onClose = vi.fn();

    render(<CashFlowModal account={demoAccount} cashAvailable="100000.0000" mode="deposit" open onClose={onClose} onCompleted={onCompleted} />);

    await userEvent.type(screen.getByLabelText("Amount"), "10000");
    await userEvent.clear(screen.getByLabelText("Trade date"));
    await userEvent.type(screen.getByLabelText("Trade date"), "2026-07-20");
    await userEvent.click(screen.getByRole("button", { name: "Deposit" }));

    await vi.waitFor(() => {
      expect(onCompleted).toHaveBeenCalledWith(result);
    });
    expect(onClose).toHaveBeenCalled();
  });

  it("shows backend errors and keeps modal open", async () => {
    depositCashMock.mockRejectedValue(new Error("Backend rejected"));

    render(<CashFlowModal account={demoAccount} cashAvailable="100000.0000" mode="deposit" open onClose={vi.fn()} onCompleted={vi.fn()} />);

    await userEvent.type(screen.getByLabelText("Amount"), "10000");
    await userEvent.clear(screen.getByLabelText("Trade date"));
    await userEvent.type(screen.getByLabelText("Trade date"), "2026-07-20");
    await userEvent.click(screen.getByRole("button", { name: "Deposit" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Backend rejected");
    expect(screen.getByRole("dialog", { name: "Deposit cash for demo" })).toBeInTheDocument();
  });
});
