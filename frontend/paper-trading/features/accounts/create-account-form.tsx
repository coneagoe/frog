"use client";

import { useState } from "react";
import { createAccount } from "@/lib/api-client";
import type { Account, CreateAccountInput } from "@/lib/types";

const feeFields = [
  { key: "commission_rate", label: "Commission rate (%)", defaultValue: "0.03", kind: "rate" },
  { key: "min_commission", label: "Minimum commission (CNY)", defaultValue: "5.00", kind: "money" },
  { key: "stamp_duty_rate", label: "Stamp duty rate (%)", defaultValue: "0.05", kind: "rate" },
  { key: "transfer_fee_rate", label: "Transfer fee rate (%)", defaultValue: "0.001", kind: "rate" }
] as const;

type FeeFieldKey = (typeof feeFields)[number]["key"];

function isNonNegativeDecimal(value: string) {
  // Only accept plain non-negative decimal strings (e.g. "0.57", ".5", "10").
  // Reject exponent notation like "1e-3" which Number() would accept but our
  // string-based percent/decimal shifters cannot handle.
  return /^\s*$|^\d+(\.\d*)?$|^\.\d+$/.test(value);
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
  // Move the last 2 digits of intPart into the front of fracPart
  const takeFromInt = Math.min(2, intPart.length);
  const moved = intPart.slice(intPart.length - takeFromInt);
  intPart = intPart.slice(0, intPart.length - takeFromInt) || "0";
  fracPart = "0".repeat(2 - takeFromInt) + moved + fracPart;
  let result = intPart + "." + fracPart;
  // Normalize: strip trailing zeros and trailing dot
  result = result.replace(/\.?0+$/, "");
  if (result === "") result = "0";
  return result;
}

export function CreateAccountForm({ onCreated }: { onCreated: (account: Account) => Promise<void> | void }) {
  const [name, setName] = useState("");
  const [initialCash, setInitialCash] = useState("100000.00");
  const [feeValues, setFeeValues] = useState<Record<FeeFieldKey, string>>({
    commission_rate: "0.03",
    min_commission: "5.00",
    stamp_duty_rate: "0.05",
    transfer_fee_rate: "0.001"
  });
  const [feeChanged, setFeeChanged] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (feeFields.some((field) => !isNonNegativeDecimal(feeValues[field.key]))) {
      setError("Fee settings must be non-negative numbers");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const input: CreateAccountInput = { name, initial_cash: initialCash };
      if (feeChanged) {
        input.fee_preset = "a_share";
        for (const field of feeFields) {
          const value = feeValues[field.key].trim();
          if (value !== "") {
            input[field.key] = field.kind === "rate" ? percentToDecimalRate(value) : value;
          }
        }
      }
      const account = await createAccount(input);
      await onCreated(account);
      setName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create account");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="form panel" onSubmit={onSubmit}>
      <h2>Create Account</h2>
      <label>
        Account name
        <input aria-label="Account name" value={name} onChange={(event) => setName(event.target.value)} required />
      </label>
      <label>
        Initial cash
        <input aria-label="Initial cash" value={initialCash} onChange={(event) => setInitialCash(event.target.value)} required />
      </label>
      <fieldset className="form__fieldset">
        <legend>Trading fee settings</legend>
        <p className="muted">Default A-share rates can be customized per account. Fees cannot be changed after creation.</p>
        <label>
          Fee preset
          <select aria-label="Fee preset" value="a_share" disabled>
            <option value="a_share">A-share default</option>
          </select>
        </label>
        {feeFields.map((field) => (
          <label key={field.key}>
            {field.label}
            <input
              aria-label={field.label}
              inputMode="decimal"
              min="0"
              placeholder={field.defaultValue}
              value={feeValues[field.key]}
              onChange={(event) => {
                setFeeChanged(true);
                setFeeValues((current) => ({ ...current, [field.key]: event.target.value }));
              }}
            />
          </label>
        ))}
      </fieldset>
      {error ? (
        <div role="alert" className="error-banner">
          {error}
        </div>
      ) : null}
      <button className="button" disabled={submitting} type="submit">
        Create account
      </button>
    </form>
  );
}
