import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createOrder } from "@/lib/api-client";
import type { Account } from "@/lib/types";
import { OrderForm } from "./order-form";

vi.mock("@/lib/api-client", () => ({
  createOrder: vi.fn()
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams()
}));

const createOrderMock = vi.mocked(createOrder);
const accounts: Account[] = [{ id: 1, name: "demo", initial_cash: "100000.00", status: "active", base_currency: "CNY" }];

describe("OrderForm", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("submits a limit order payload", async () => {
    const onSubmitted = vi.fn();
    createOrderMock.mockResolvedValue({
      id: 1,
      account_id: 1,
      symbol: "000001.SZ",
      side: "buy",
      quantity: 100,
      limit_price: "10.00",
      trade_date: "2026-06-16",
      status: "accepted",
      filled_quantity: 0,
      frozen_cash: "1000.00",
      frozen_quantity: 0,
      rejection_code: null,
      rejection_reason: null
    });

    render(<OrderForm accounts={accounts} selectedAccountId={1} onSubmitted={onSubmitted} />);

    await userEvent.type(screen.getByLabelText("Symbol"), "000001.SZ");
    await userEvent.clear(screen.getByLabelText("Quantity"));
    await userEvent.type(screen.getByLabelText("Quantity"), "100");
    await userEvent.clear(screen.getByLabelText("Limit price"));
    await userEvent.type(screen.getByLabelText("Limit price"), "10.00");
    await userEvent.type(screen.getByLabelText("Trade date"), "2026-06-16");
    await userEvent.click(screen.getByRole("button", { name: "Submit order" }));

    expect(createOrderMock).toHaveBeenCalledWith(1, {
      symbol: "000001.SZ",
      side: "buy",
      quantity: 100,
      limit_price: "10.00",
      trade_date: "2026-06-16"
    });
    expect(onSubmitted).toHaveBeenCalled();
  });

  it("sends comment when provided and clears input after submit", async () => {
    const onSubmitted = vi.fn();
    createOrderMock.mockResolvedValue({
      id: 1,
      account_id: 1,
      symbol: "000001.SZ",
      side: "buy",
      quantity: 100,
      limit_price: "10.00",
      trade_date: "2026-06-16",
      status: "accepted",
      filled_quantity: 0,
      frozen_cash: "1000.00",
      frozen_quantity: 0,
      rejection_code: null,
      rejection_reason: null,
      comment: "突破买入"
    });

    render(<OrderForm accounts={accounts} selectedAccountId={1} onSubmitted={onSubmitted} />);

    await userEvent.type(screen.getByLabelText("Symbol"), "000001.SZ");
    await userEvent.clear(screen.getByLabelText("Quantity"));
    await userEvent.type(screen.getByLabelText("Quantity"), "100");
    await userEvent.clear(screen.getByLabelText("Limit price"));
    await userEvent.type(screen.getByLabelText("Limit price"), "10.00");
    await userEvent.type(screen.getByLabelText("Trade date"), "2026-06-16");
    await userEvent.type(screen.getByLabelText("Comment"), "突破买入");
    await userEvent.click(screen.getByRole("button", { name: "Submit order" }));

    expect(createOrderMock).toHaveBeenCalledWith(1, {
      symbol: "000001.SZ",
      side: "buy",
      quantity: 100,
      limit_price: "10.00",
      trade_date: "2026-06-16",
      comment: "突破买入"
    });
    expect(onSubmitted).toHaveBeenCalled();
    expect(screen.getByLabelText("Comment")).toHaveValue("");
  });

  it("does not send comment when input is empty", async () => {
    const onSubmitted = vi.fn();
    createOrderMock.mockResolvedValue({
      id: 1,
      account_id: 1,
      symbol: "000001.SZ",
      side: "buy",
      quantity: 100,
      limit_price: "10.00",
      trade_date: "2026-06-16",
      status: "accepted",
      filled_quantity: 0,
      frozen_cash: "1000.00",
      frozen_quantity: 0,
      rejection_code: null,
      rejection_reason: null
    });

    render(<OrderForm accounts={accounts} selectedAccountId={1} onSubmitted={onSubmitted} />);

    await userEvent.type(screen.getByLabelText("Symbol"), "000001.SZ");
    await userEvent.clear(screen.getByLabelText("Quantity"));
    await userEvent.type(screen.getByLabelText("Quantity"), "100");
    await userEvent.clear(screen.getByLabelText("Limit price"));
    await userEvent.type(screen.getByLabelText("Limit price"), "10.00");
    await userEvent.type(screen.getByLabelText("Trade date"), "2026-06-16");
    await userEvent.click(screen.getByRole("button", { name: "Submit order" }));

    expect(createOrderMock).toHaveBeenCalledWith(1, {
      symbol: "000001.SZ",
      side: "buy",
      quantity: 100,
      limit_price: "10.00",
      trade_date: "2026-06-16"
    });
  });

  it("keeps the native calendar and hints yyyy/mm/dd display", async () => {
    const onSubmitted = vi.fn();
    createOrderMock.mockResolvedValue({
      id: 1,
      account_id: 1,
      symbol: "000001.SZ",
      side: "buy",
      quantity: 100,
      limit_price: "10.00",
      trade_date: "2026-06-16",
      status: "accepted",
      filled_quantity: 0,
      frozen_cash: "1000.00",
      frozen_quantity: 0,
      rejection_code: null,
      rejection_reason: null
    });

    render(<OrderForm accounts={accounts} selectedAccountId={1} onSubmitted={onSubmitted} />);

    const tradeDateInput = screen.getByLabelText("Trade date");
    expect(tradeDateInput).toHaveAttribute("type", "date");
    expect(tradeDateInput).toHaveAttribute("lang", "en-ZA");

    await userEvent.type(screen.getByLabelText("Symbol"), "000001.SZ");
    await userEvent.clear(screen.getByLabelText("Quantity"));
    await userEvent.type(screen.getByLabelText("Quantity"), "100");
    await userEvent.clear(screen.getByLabelText("Limit price"));
    await userEvent.type(screen.getByLabelText("Limit price"), "10.00");
    await userEvent.type(tradeDateInput, "2026-06-16");
    await userEvent.click(screen.getByRole("button", { name: "Submit order" }));

    expect(createOrderMock).toHaveBeenCalledWith(1, expect.objectContaining({ trade_date: "2026-06-16" }));
  });

  it("warns for non-lot quantities", async () => {
    render(<OrderForm accounts={accounts} selectedAccountId={1} onSubmitted={vi.fn()} />);

    await userEvent.clear(screen.getByLabelText("Quantity"));
    await userEvent.type(screen.getByLabelText("Quantity"), "101");

    expect(screen.getByText("A-share orders should use 100-share lots.")).toBeInTheDocument();
  });

  it("does not submit invalid required fields", async () => {
    render(<OrderForm accounts={accounts} selectedAccountId={1} onSubmitted={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: "Submit order" }));

    expect(createOrderMock).not.toHaveBeenCalled();
  });

  it("uses the latest selected account", async () => {
    createOrderMock.mockResolvedValue({
      id: 1,
      account_id: 2,
      symbol: "000001.SZ",
      side: "buy",
      quantity: 100,
      limit_price: "10.00",
      trade_date: "2026-06-16",
      status: "accepted",
      filled_quantity: 0,
      frozen_cash: "1000.00",
      frozen_quantity: 0,
      rejection_code: null,
      rejection_reason: null
    });
    const { rerender } = render(<OrderForm accounts={accounts} selectedAccountId={1} onSubmitted={vi.fn()} />);
    rerender(
      <OrderForm
        accounts={[...accounts, { id: 2, name: "second", initial_cash: "200000.00", status: "active", base_currency: "CNY" }]}
        selectedAccountId={2}
        onSubmitted={vi.fn()}
      />
    );

    await userEvent.type(screen.getByLabelText("Symbol"), "000001.SZ");
    await userEvent.clear(screen.getByLabelText("Quantity"));
    await userEvent.type(screen.getByLabelText("Quantity"), "100");
    await userEvent.clear(screen.getByLabelText("Limit price"));
    await userEvent.type(screen.getByLabelText("Limit price"), "10.00");
    await userEvent.type(screen.getByLabelText("Trade date"), "2026-06-16");
    await userEvent.click(screen.getByRole("button", { name: "Submit order" }));

    expect(createOrderMock).toHaveBeenCalledWith(2, expect.any(Object));
  });
});
