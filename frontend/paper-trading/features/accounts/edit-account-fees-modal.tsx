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
  // Only accept plain non-negative decimal strings (e.g. "0.57", ".5", "10").
  // Reject exponent notation like "1e-3" which Number() would accept but our
  // string-based percent/decimal shifters cannot handle.
  return /^\s*$|^\d+(\.\d*)?$|^\.\d+$/.test(value);
}

function decimalRateToPercent(value: string): string {
  // String-safe conversion: move decimal point 2 places right.
  // Avoids floating-point artifacts like 0.5700000000000001 from Number("0.0057") * 100.
  const s = value.trim();
  if (s === "") return "";
  const dotIdx = s.indexOf(".");
  let intPart: string;
  let fracPart: string;
  if (dotIdx === -1) {
    intPart = s;
    fracPart = "";
  } else {
    intPart = s.slice(0, dotIdx);
    fracPart = s.slice(dotIdx + 1);
  }
  // Move the first 2 digits of fracPart to the end of intPart
  const takeFromFrac = Math.min(2, fracPart.length);
  const moved = fracPart.slice(0, takeFromFrac);
  fracPart = fracPart.slice(takeFromFrac);
  intPart = intPart + moved + "0".repeat(2 - takeFromFrac);
  let result: string;
  if (fracPart === "") {
    result = intPart;
  } else {
    result = intPart + "." + fracPart;
  }
  // Normalize: strip leading zeros (keep at least 1 digit before decimal)
  const rDotIdx = result.indexOf(".");
  if (rDotIdx >= 0) {
    const before = result.slice(0, rDotIdx).replace(/^0+/, "") || "0";
    result = before + result.slice(rDotIdx);
  } else {
    result = result.replace(/^0+/, "") || "0";
  }
  // Strip trailing zeros after decimal and trailing dot
  result = result.replace(/\.?0+$/, "");
  if (result.startsWith(".")) result = "0" + result;
  return result;
}

function percentToDecimalRate(value: string): string {
  // String-safe conversion: move decimal point 2 places left.
  // Avoids floating-point artifacts like 0.0057000000000000005 from Number("0.57") / 100.
  const s = value.trim();
  if (s === "") return "";
  const dotIdx = s.indexOf(".");
  let intPart: string;
  let fracPart: string;
  if (dotIdx === -1) {
    intPart = s;
    fracPart = "";
  } else {
    intPart = s.slice(0, dotIdx);
    fracPart = s.slice(dotIdx + 1);
  }
  const takeFromInt = Math.min(2, intPart.length);
  const moved = intPart.slice(intPart.length - takeFromInt);
  intPart = intPart.slice(0, intPart.length - takeFromInt) || "0";
  fracPart = "0".repeat(2 - takeFromInt) + moved + fracPart;
  let result = intPart + "." + fracPart;
  result = result.replace(/\.?0+$/, "");
  if (result === "") result = "0";
  return result;
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
