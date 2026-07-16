"use client";

import { useEffect, useState } from "react";
import { updateAccountFees } from "@/lib/api-client";
import type { Account, UpdateAccountFeesInput } from "@/lib/types";

const feeFields = [
  { key: "commission_rate", label: "Commission rate" },
  { key: "min_commission", label: "Minimum commission (CNY)" },
  { key: "stamp_duty_rate", label: "Stamp duty rate" },
  { key: "transfer_fee_rate", label: "Transfer fee rate" }
] as const;

const feeFieldKeys = feeFields.map((f) => f.key);

type FeeFieldKey = (typeof feeFields)[number]["key"];

function isNonNegativeDecimal(value: string) {
  return value.trim() === "" || (!Number.isNaN(Number(value)) && Number(value) >= 0);
}

type EditAccountFeesModalProps = {
  account: Account | null;
  open: boolean;
  onClose: () => void;
  onSaved: (account: Account) => Promise<void> | void;
};

export function EditAccountFeesModal({ account, open, onClose, onSaved }: EditAccountFeesModalProps) {
  const [feeValues, setFeeValues] = useState<Record<FeeFieldKey, string>>({
    commission_rate: "",
    min_commission: "",
    stamp_duty_rate: "",
    transfer_fee_rate: ""
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Reset form when modal opens with a new account
  useEffect(() => {
    if (account && open) {
      setFeeValues({
        commission_rate: account.commission_rate,
        min_commission: account.min_commission,
        stamp_duty_rate: account.stamp_duty_rate,
        transfer_fee_rate: account.transfer_fee_rate
      });
      setError(null);
      setSubmitting(false);
    }
  }, [account, open]);

  if (!account || !open) {
    return null;
  }

  // Determine whether at least one field has actually changed
  const hasChanges = feeFieldKeys.some((key) => feeValues[key].trim() !== account[key]);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();

    // Client-side validation
    if (feeFieldKeys.some((key) => !isNonNegativeDecimal(feeValues[key]))) {
      setError("Fee settings must be non-negative numbers");
      return;
    }

    // No changes — early return to avoid calling the API with an empty diff
    if (!hasChanges) {
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      // Build payload with only changed fields
      const input: UpdateAccountFeesInput = {};
      for (const key of feeFieldKeys) {
        const trimmed = feeValues[key].trim();
        if (trimmed !== account[key]) {
          input[key] = trimmed;
        }
      }

      const updatedAccount = await updateAccountFees(account.id, input);
      await onSaved(updatedAccount);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update fees");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Edit fees">
        <div className="modal__header">
          <h2>Edit fees — {account.name}</h2>
        </div>
        <form onSubmit={onSubmit}>
          <div className="modal__body">
            <div className="form">
              {feeFields.map((field) => (
                <label key={field.key}>
                  {field.label}
                  <input
                    aria-label={field.label}
                    inputMode="decimal"
                    min="0"
                    value={feeValues[field.key]}
                    onChange={(event) => {
                      setError(null);
                      setFeeValues((current) => ({ ...current, [field.key]: event.target.value }));
                    }}
                  />
                </label>
              ))}
            </div>
            <p className="modal__note">
              Fee changes affect future orders and trades only; existing trades, cash ledger entries, and
              snapshots are not recalculated.
            </p>
            {error ? (
              <div role="alert" className="error-banner">
                {error}
              </div>
            ) : null}
          </div>
          <div className="modal__footer">
            <button className="button button--secondary" onClick={onClose} type="button">
              Cancel
            </button>
            <button className="button" disabled={submitting || !hasChanges} type="submit">
              {submitting ? "Saving…" : "Save changes"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
