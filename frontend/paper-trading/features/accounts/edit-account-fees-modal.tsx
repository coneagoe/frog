"use client";

import { useEffect, useState } from "react";
import { updateAccountFees } from "@/lib/api-client";
import type { Account, UpdateAccountFeesInput } from "@/lib/types";

const feeFields = [
  { key: "commission_rate", label: "Commission rate (%)", kind: "rate" },
  { key: "min_commission", label: "Minimum commission (CNY)", kind: "money" },
  { key: "stamp_duty_rate", label: "Stamp duty rate (%)", kind: "rate" },
  { key: "transfer_fee_rate", label: "Transfer fee rate (%)", kind: "rate" }
] as const;

const feeFieldKeys = feeFields.map((f) => f.key);

type FeeFieldKey = (typeof feeFields)[number]["key"];

function isNonNegativeDecimal(value: string) {
  return value.trim() === "" || (!Number.isNaN(Number(value)) && Number(value) >= 0);
}

function decimalRateToPercent(value: string) {
  return (Number(value) * 100).toString();
}

function percentToDecimalRate(value: string) {
  return (Number(value) / 100).toString();
}

function displayValueForField(key: FeeFieldKey, value: string) {
  const field = feeFields.find((item) => item.key === key);
  return field?.kind === "rate" ? decimalRateToPercent(value) : value;
}

function apiValueForField(key: FeeFieldKey, value: string) {
  const field = feeFields.find((item) => item.key === key);
  return field?.kind === "rate" ? percentToDecimalRate(value) : value;
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
        commission_rate: displayValueForField("commission_rate", account.commission_rate),
        min_commission: displayValueForField("min_commission", account.min_commission),
        stamp_duty_rate: displayValueForField("stamp_duty_rate", account.stamp_duty_rate),
        transfer_fee_rate: displayValueForField("transfer_fee_rate", account.transfer_fee_rate)
      });
      setError(null);
      setSubmitting(false);
    }
  }, [account, open]);

  if (!account || !open) {
    return null;
  }

  // Determine whether at least one field has actually changed to a non-empty value
  const hasChanges = feeFieldKeys.some((key) => {
    const trimmed = feeValues[key].trim();
    return trimmed !== "" && trimmed !== displayValueForField(key, account[key]);
  });

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();

    // Non-null assertion is safe: the early return above guarantees account is set
    const acct = account!;

    // Client-side validation
    if (feeFieldKeys.some((key) => !isNonNegativeDecimal(feeValues[key]))) {
      setError("Fee settings must be non-negative numbers");
      return;
    }

    // No changes — early return to avoid calling the API with an empty diff
    if (!hasChanges) {
      setError("Change at least one fee field before saving.");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      // Build payload with only changed fields; omit empty strings
      const input: UpdateAccountFeesInput = {};
      for (const key of feeFieldKeys) {
        const trimmed = feeValues[key].trim();
        if (trimmed !== "" && trimmed !== displayValueForField(key, acct[key])) {
          input[key] = apiValueForField(key, trimmed);
        }
      }

      const updatedAccount = await updateAccountFees(acct.id, input);
      await onSaved(updatedAccount);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update fees");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label={"Edit fees for " + account.name}>
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
            <button className="button" disabled={submitting} type="submit">
              {submitting ? "Saving…" : "Save fees"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
