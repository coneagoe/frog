import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { updateAccountFees } from "@/lib/api-client";
import { EditAccountFeesModal } from "./edit-account-fees-modal";

const updateAccountFeesMock = vi.mocked(updateAccountFees);

vi.mock("@/lib/api-client", () => ({
  updateAccountFees: vi.fn()
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

describe("EditAccountFeesModal", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("prefills the current fee values when opened", async () => {
    render(<EditAccountFeesModal account={demoAccount} open onClose={vi.fn()} onSaved={vi.fn()} />);

    expect(screen.getByLabelText("Commission rate")).toHaveValue("0.000300");
    expect(screen.getByLabelText("Minimum commission (CNY)")).toHaveValue("5.00");
    expect(screen.getByLabelText("Stamp duty rate")).toHaveValue("0.000500");
    expect(screen.getByLabelText("Transfer fee rate")).toHaveValue("0.000010");
  });

  it("sends only changed fee fields on save", async () => {
    const updatedAccount = { ...demoAccount, commission_rate: "0.0002", min_commission: "3.00" };
    updateAccountFeesMock.mockResolvedValue(updatedAccount);
    const onSaved = vi.fn();

    render(<EditAccountFeesModal account={demoAccount} open onClose={vi.fn()} onSaved={onSaved} />);
    await userEvent.clear(screen.getByLabelText("Commission rate"));
    await userEvent.type(screen.getByLabelText("Commission rate"), "0.0002");
    await userEvent.clear(screen.getByLabelText("Minimum commission (CNY)"));
    await userEvent.type(screen.getByLabelText("Minimum commission (CNY)"), "3.00");
    await userEvent.click(screen.getByRole("button", { name: "Save fees" }));

    expect(updateAccountFeesMock).toHaveBeenCalledWith(1, {
      commission_rate: "0.0002",
      min_commission: "3.00"
    });
    expect(onSaved).toHaveBeenCalledWith(updatedAccount);
  });

  it("does not call the API when nothing changed", async () => {
    render(<EditAccountFeesModal account={demoAccount} open onClose={vi.fn()} onSaved={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: "Save fees" }));

    expect(updateAccountFeesMock).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Change at least one fee field before saving.");
  });

  it("omits cleared (empty) fields from the submitted payload", async () => {
    const updatedAccount = { ...demoAccount, min_commission: "3.00" };
    updateAccountFeesMock.mockResolvedValue(updatedAccount);
    const onSaved = vi.fn();

    render(<EditAccountFeesModal account={demoAccount} open onClose={vi.fn()} onSaved={onSaved} />);
    // Clear commission_rate to empty and change min_commission to a new value
    await userEvent.clear(screen.getByLabelText("Commission rate"));
    await userEvent.clear(screen.getByLabelText("Minimum commission (CNY)"));
    await userEvent.type(screen.getByLabelText("Minimum commission (CNY)"), "3.00");
    await userEvent.click(screen.getByRole("button", { name: "Save fees" }));

    // The cleared commission_rate should NOT be in the payload
    expect(updateAccountFeesMock).toHaveBeenCalledWith(1, {
      min_commission: "3.00"
    });
    expect(updateAccountFeesMock.mock.calls[0][1]).not.toHaveProperty("commission_rate");
    expect(onSaved).toHaveBeenCalledWith(updatedAccount);
  });

  it("does not call the API when clearing a field is the only effective change", async () => {
    render(<EditAccountFeesModal account={demoAccount} open onClose={vi.fn()} onSaved={vi.fn()} />);
    // Clear commission_rate to empty — the only "change"
    await userEvent.clear(screen.getByLabelText("Commission rate"));
    await userEvent.click(screen.getByRole("button", { name: "Save fees" }));

    expect(updateAccountFeesMock).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Change at least one fee field before saving.");
  });

  it("keeps the modal open and shows a server error", async () => {
    updateAccountFeesMock.mockRejectedValue(new Error("Invalid decimal"));

    render(<EditAccountFeesModal account={demoAccount} open onClose={vi.fn()} onSaved={vi.fn()} />);
    await userEvent.clear(screen.getByLabelText("Commission rate"));
    await userEvent.type(screen.getByLabelText("Commission rate"), "0.0002");
    await userEvent.click(screen.getByRole("button", { name: "Save fees" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid decimal");
    expect(screen.getByRole("dialog", { name: "Edit fees for demo" })).toBeInTheDocument();
  });
});
