import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createCorporateAction } from "@/lib/api-client";
import { CorporateActionModal } from "./corporate-action-modal";

vi.mock("@/lib/api-client", () => ({ createCorporateAction: vi.fn() }));

const createCorporateActionMock = vi.mocked(createCorporateAction);
const account = {
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
const result = { event: {}, impact: {}, recalculation: {} } as never;

async function fillCommonFields(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Symbol"), "000001.SZ");
  await user.clear(screen.getByLabelText("Event time"));
  await user.type(screen.getByLabelText("Event time"), "2026-08-27T09:30:00+08:00");
  await user.type(screen.getByLabelText("Idempotency key"), "action-1");
}

describe("CorporateActionModal", () => {
  beforeEach(() => vi.resetAllMocks());

  it("focuses on open, restores focus, and closes with Escape", async () => {
    const user = userEvent.setup();
    const opener = document.createElement("button");
    document.body.append(opener);
    opener.focus();
    const onClose = vi.fn();
    const { unmount } = render(<CorporateActionModal account={account} open onClose={onClose} onCompleted={vi.fn()} />);

    await waitFor(() => expect(screen.getByLabelText("Symbol")).toHaveFocus());
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
    unmount();
    expect(opener).toHaveFocus();
    opener.remove();
  });

  it.each([
    ["dividend", "Per-share amount", "1.2", { per_share_amount: "1.2" }],
    ["split", "Ratio", "2", { ratio: "2" }],
    ["reverse_split", "Ratio", "0.5", { ratio: "0.5" }],
    ["bonus_share", "Bonus ratio", "0.1", { bonus_ratio: "0.1" }],
    ["rights_issue", "Subscription ratio", "0.1", { subscription_ratio: "0.1", subscription_price: "3" }]
  ] as const)("submits the %s payload", async (eventType, field, value, parameters) => {
    const user = userEvent.setup();
    createCorporateActionMock.mockResolvedValue(result);
    const onClose = vi.fn();
    render(<CorporateActionModal account={account} open onClose={onClose} onCompleted={vi.fn()} />);
    await fillCommonFields(user);
    await user.selectOptions(screen.getByLabelText("Action type"), eventType);
    await user.type(screen.getByLabelText(field), value);
    if (eventType === "rights_issue") await user.type(screen.getByLabelText("Subscription price"), "3");
    await user.click(screen.getByRole("button", { name: "Apply action" }));

    await waitFor(() => expect(createCorporateActionMock).toHaveBeenCalledWith(1, expect.objectContaining({ event_type: eventType, parameters })));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("validates required fields, reverse splits, and rights cash requirements", async () => {
    const user = userEvent.setup();
    render(<CorporateActionModal account={account} open onClose={vi.fn()} onCompleted={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Apply action" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Symbol is required");

    await fillCommonFields(user);
    await user.selectOptions(screen.getByLabelText("Action type"), "reverse_split");
    await user.type(screen.getByLabelText("Ratio"), "1");
    await user.click(screen.getByRole("button", { name: "Apply action" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Reverse split ratio must be below 1");

    await user.selectOptions(screen.getByLabelText("Action type"), "rights_issue");
    await user.type(screen.getByLabelText("Subscription ratio"), "0.1");
    expect(screen.getByRole("note")).toHaveTextContent("Available cash: 100000.0000");
    await user.click(screen.getByRole("button", { name: "Apply action" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Subscription price must be greater than 0 and finite");
    expect(createCorporateActionMock).not.toHaveBeenCalled();
  });

  it("keeps backend errors and the dialog open, and blocks backdrop dismissal in flight", async () => {
    const user = userEvent.setup();
    let reject!: (error: Error) => void;
    createCorporateActionMock.mockReturnValue(new Promise((_, nextReject) => { reject = nextReject; }));
    const onClose = vi.fn();
    render(<CorporateActionModal account={account} open onClose={onClose} onCompleted={vi.fn()} />);
    await fillCommonFields(user);
    await user.type(screen.getByLabelText("Per-share amount"), "1");
    await user.click(screen.getByRole("button", { name: "Apply action" }));
    await user.click(screen.getByTestId("corporate-action-backdrop"));
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Applying…" })).toBeDisabled();
    reject(new Error("Backend rejected"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Backend rejected");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("awaits account refresh before closing", async () => {
    const user = userEvent.setup();
    let resolveCompletion!: () => void;
    const onCompleted = vi.fn(() => new Promise<void>((resolve) => { resolveCompletion = resolve; }));
    const onClose = vi.fn();
    createCorporateActionMock.mockResolvedValue(result);
    render(<CorporateActionModal account={account} open onClose={onClose} onCompleted={onCompleted} />);
    await fillCommonFields(user);
    await user.type(screen.getByLabelText("Per-share amount"), "1");
    await user.click(screen.getByRole("button", { name: "Apply action" }));
    await waitFor(() => expect(onCompleted).toHaveBeenCalledWith(result));
    expect(onClose).not.toHaveBeenCalled();
    resolveCompletion();
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it("retains completion callback errors and keeps the modal open", async () => {
    const user = userEvent.setup();
    createCorporateActionMock.mockResolvedValue(result);
    const onClose = vi.fn();
    render(<CorporateActionModal account={account} open onClose={onClose} onCompleted={vi.fn().mockRejectedValue(new Error("Refresh failed"))} />);
    await fillCommonFields(user);
    await user.type(screen.getByLabelText("Per-share amount"), "1");
    await user.click(screen.getByRole("button", { name: "Apply action" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Refresh failed");
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
