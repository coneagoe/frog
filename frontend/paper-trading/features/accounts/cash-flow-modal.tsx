"use client";

import { useState } from "react";
import { ErrorBanner } from "@/components/error-banner";
import { depositCash, withdrawCash } from "@/lib/api-client";
import type { Account, CashFlowResult } from "@/lib/types";

type Props = {
  account: Account | null;
  cashAvailable: string;
  mode: "deposit" | "withdraw";
  open: boolean;
  onClose: () => void;
  onCompleted: (result: CashFlowResult) => Promise<void> | void;
};

export function CashFlowModal({ account, cashAvailable, mode, open, onClose, onCompleted }: Props) {
  const [amount, setAmount] = useState("");
  const [tradeDate, setTradeDate] = useState(new Date().toISOString().slice(0, 10));
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!open || !account) {
    return null;
  }

  const currentAccount = account;
  const title = mode === "deposit" ? `Deposit cash for ${currentAccount.name}` : `Withdraw cash from ${currentAccount.name}`;
  const buttonLabel = mode === "deposit" ? "Deposit" : "Withdraw";

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    const numericAmount = Number(amount);
    if (!Number.isFinite(numericAmount) || numericAmount <= 0) {
      setError("Amount must be greater than 0");
      return;
    }

    if (mode === "withdraw" && numericAmount > Number(cashAvailable)) {
      setError(`Amount cannot exceed available cash ${cashAvailable}`);
      return;
    }

    setSubmitting(true);
    try {
      const payload = { amount, trade_date: tradeDate, ...(note.trim() ? { note: note.trim() } : {}) };
      const result = mode === "deposit" ? await depositCash(currentAccount.id, payload) : await withdrawCash(currentAccount.id, payload);
      await onCompleted(result);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to ${mode} cash`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal__header">
          <h2>{title}</h2>
        </div>
        <form onSubmit={onSubmit}>
          <div className="modal__body">
            {mode === "withdraw" ? <p className="muted">Maximum withdrawable: {cashAvailable}</p> : null}
            {error ? <ErrorBanner message={error} /> : null}
            <div className="form">
              <label>
                Amount
                <input aria-label="Amount" inputMode="decimal" min="0" value={amount} onChange={(event) => setAmount(event.target.value)} />
              </label>
              <label>
                Trade date
                <input aria-label="Trade date" type="date" value={tradeDate} onChange={(event) => setTradeDate(event.target.value)} />
              </label>
              <label>
                Note
                <textarea aria-label="Note" value={note} onChange={(event) => setNote(event.target.value)} />
              </label>
            </div>
          </div>
          <div className="modal__footer">
            <button className="button button--secondary" onClick={onClose} type="button">
              Cancel
            </button>
            <button className="button" disabled={submitting} type="submit">
              {submitting ? "Submitting…" : buttonLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
