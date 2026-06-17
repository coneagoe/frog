"use client";

import { useState } from "react";
import { createAccount } from "@/lib/api-client";
import type { Account } from "@/lib/types";

export function CreateAccountForm({ onCreated }: { onCreated: (account: Account) => Promise<void> | void }) {
  const [name, setName] = useState("");
  const [initialCash, setInitialCash] = useState("100000.00");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const account = await createAccount({ name, initial_cash: initialCash });
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
