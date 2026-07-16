"use client";

import { useState } from "react";
import { createAccount } from "@/lib/api-client";
import type { Account, CreateAccountInput } from "@/lib/types";

const feeFields = [
  { key: "commission_rate", label: "Commission rate", defaultValue: "0.0003" },
  { key: "min_commission", label: "Minimum commission (CNY)", defaultValue: "5.00" },
  { key: "stamp_duty_rate", label: "Stamp duty rate", defaultValue: "0.0005" },
  { key: "transfer_fee_rate", label: "Transfer fee rate", defaultValue: "0.00001" }
] as const;

type FeeFieldKey = (typeof feeFields)[number]["key"];

function isNonNegativeDecimal(value: string) {
  return value.trim() === "" || (!Number.isNaN(Number(value)) && Number(value) >= 0);
}

export function CreateAccountForm({ onCreated }: { onCreated: (account: Account) => Promise<void> | void }) {
  const [name, setName] = useState("");
  const [initialCash, setInitialCash] = useState("100000.00");
  const [feeValues, setFeeValues] = useState<Record<FeeFieldKey, string>>({
    commission_rate: "0.0003",
    min_commission: "5.00",
    stamp_duty_rate: "0.0005",
    transfer_fee_rate: "0.00001"
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
            input[field.key] = value;
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
