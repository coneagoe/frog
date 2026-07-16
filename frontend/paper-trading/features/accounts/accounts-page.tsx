"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ErrorBanner } from "@/components/error-banner";
import { deleteAccount, listAccounts, listCashLedger, listPositions } from "@/lib/api-client";
import type { Account, CashLedgerEntry, Position } from "@/lib/types";
import { CashLedgerTable, PositionTable } from "../trading/trading-tables";
import { AccountList } from "./account-list";
import { CreateAccountForm } from "./create-account-form";
import { EditAccountFeesModal } from "./edit-account-fees-modal";

export function AccountsPage() {
  const searchParams = useSearchParams();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [cashLedger, setCashLedger] = useState<CashLedgerEntry[]>([]);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [feeEditorAccount, setFeeEditorAccount] = useState<Account | null>(null);
  const [feeEditorOpen, setFeeEditorOpen] = useState(false);
  const requestIdRef = useRef(0);
  const lastUrlParamRef = useRef<string | null>(null);

  const selectedAccount = accounts.find((a) => a.id === selectedAccountId) ?? null;

  async function loadAccountDetails(accountId: number, clearExisting = false) {
    if (!accountId) {
      return;
    }
    const requestId = ++requestIdRef.current;
    setDetailError(null);
    if (clearExisting) {
      setPositions([]);
      setCashLedger([]);
    }
    const [nextPositions, nextCashLedger] = await Promise.allSettled([
      listPositions(accountId),
      listCashLedger(accountId)
    ]);

    if (requestId !== requestIdRef.current) {
      return;
    }

    const errors: string[] = [];

    if (nextPositions.status === "fulfilled") {
      setPositions(nextPositions.value);
    } else {
      errors.push(nextPositions.reason instanceof Error ? nextPositions.reason.message : "Failed to load positions");
    }
    if (nextCashLedger.status === "fulfilled") {
      setCashLedger(nextCashLedger.value);
    } else {
      errors.push(nextCashLedger.reason instanceof Error ? nextCashLedger.reason.message : "Failed to load cash ledger");
    }

    if (errors.length > 0) {
      setDetailError(errors.join("; "));
    }
  }

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

  // After accounts load/refresh/delete, ensure a valid account is selected
  // and stale detail panels are not shown for deleted accounts.
  // Also react to ?accountId URL param changes (tracked via lastUrlParamRef so
  // that only real URL navigation triggers a switch, not manual View clicks which
  // change selectedAccountId but leave the URL param unchanged).
  useEffect(() => {
    if (accounts.length === 0) {
      setSelectedAccountId(null);
      setPositions([]);
      setCashLedger([]);
      setDetailError(null);
      return;
    }

    const currentUrlParam = searchParams.get("accountId");
    const requestedAccountId = Number(currentUrlParam);
    const paramIsValid = !Number.isNaN(requestedAccountId) && accounts.some((a) => a.id === requestedAccountId);

    // URL param changed (real navigation) — apply it even over manual selection
    if (currentUrlParam !== lastUrlParamRef.current) {
      lastUrlParamRef.current = currentUrlParam;
      if (paramIsValid && requestedAccountId !== selectedAccountId) {
        setSelectedAccountId(requestedAccountId);
        void loadAccountDetails(requestedAccountId, true);
        return;
      }
    }

    // No valid selection yet (initial load or deleted selection)
    if (selectedAccountId === null || !accounts.find((a) => a.id === selectedAccountId)) {
      const targetId = paramIsValid ? requestedAccountId : accounts[0].id;
      lastUrlParamRef.current = currentUrlParam;
      setSelectedAccountId(targetId);
      void loadAccountDetails(targetId, true);
    }
  }, [accounts, selectedAccountId, loading, searchParams]);

  async function onSelect(account: Account) {
    setSelectedAccountId(account.id);
    await loadAccountDetails(account.id, true);
  }

  async function onCreated() {
    await refreshAccounts();
  }

  async function handleFeeSaved(updatedAccount: Account) {
    setFeeEditorOpen(false);
    setFeeEditorAccount(null);
    await refreshAccounts();
    void loadAccountDetails(updatedAccount.id, true);
  }

  // Close fee editor if the selected account is no longer valid
  useEffect(() => {
    if (feeEditorOpen && (accounts.length === 0 || !accounts.find((a) => a.id === feeEditorAccount?.id))) {
      setFeeEditorOpen(false);
      setFeeEditorAccount(null);
    }
  }, [accounts, feeEditorAccount?.id, feeEditorOpen]);

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
          {error ? <ErrorBanner message={error} /> : <AccountList accounts={accounts} selectedAccountId={selectedAccountId} onSelect={onSelect} onDelete={onDelete} />}
        </section>
      </div>
      {selectedAccountId ? (
        <div>
          <div className="panel__header">
            <h2>{selectedAccount?.name ?? `Account #${selectedAccountId}`}</h2>
            {selectedAccount ? (
              <button
                className="button button--secondary"
                onClick={() => {
                  setFeeEditorAccount(selectedAccount);
                  setFeeEditorOpen(true);
                }}
                type="button"
              >
                Edit fees
              </button>
            ) : null}
          </div>
          {detailError ? <ErrorBanner message={detailError} /> : null}
          <div className="grid grid--two">
            <section className="panel">
              <h2>Positions</h2>
              <PositionTable positions={positions} />
            </section>
            <section className="panel">
              <h2>Cash Ledger</h2>
              <CashLedgerTable entries={cashLedger} />
            </section>
          </div>
        </div>
      ) : null}
      <EditAccountFeesModal
        account={feeEditorAccount}
        open={feeEditorOpen}
        onClose={() => {
          setFeeEditorOpen(false);
          setFeeEditorAccount(null);
        }}
        onSaved={handleFeeSaved}
      />
    </section>
  );
}
