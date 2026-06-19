"use client";

import { useEffect, useState } from "react";
import { ErrorBanner } from "@/components/error-banner";
import { deleteAccount, listAccounts } from "@/lib/api-client";
import type { Account } from "@/lib/types";
import { AccountList } from "./account-list";
import { CreateAccountForm } from "./create-account-form";

export function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function refreshAccounts() {
    try {
      setError(null);
      const nextAccounts = await listAccounts();
      setAccounts(nextAccounts);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load accounts");
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function loadAccounts() {
      setLoading(true);
      try {
        const nextAccounts = await listAccounts();
        if (!cancelled) {
          setAccounts(nextAccounts);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load accounts");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadAccounts();
    return () => {
      cancelled = true;
    };
  }, []);

  async function onCreated() {
    await refreshAccounts();
  }

  async function onDelete(account: Account) {
    const confirmed = window.confirm(
      `Delete paper account ${account.name}? This permanently removes all related trading data.`
    );
    if (!confirmed) {
      return;
    }
    try {
      setError(null);
      await deleteAccount(account.id);
      await refreshAccounts();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete account");
    }
  }

  return (
    <section className="page">
      <div className="page__header">
        <div>
          <h1>Accounts</h1>
          <p className="muted">Create accounts and open a trading or analytics workspace.</p>
        </div>
      </div>
      <div className="grid grid--two accounts-grid">
        <CreateAccountForm onCreated={onCreated} />
        <section className="panel">
          <div className="panel__header">
            <h2>Paper Accounts</h2>
            <button className="button button--secondary" onClick={() => void refreshAccounts()} type="button">
              Refresh
            </button>
          </div>
          {loading ? <p className="muted">Loading paper trading data...</p> : null}
          {error ? <ErrorBanner message={error} /> : <AccountList accounts={accounts} onDelete={onDelete} />}
        </section>
      </div>
    </section>
  );
}
