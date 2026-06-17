"use client";

import { useEffect, useState } from "react";
import { ErrorBanner } from "@/components/error-banner";
import { cancelOrder, listAccounts, listCashLedger, listOrders, listPositions, listTrades } from "@/lib/api-client";
import type { Account, CashLedgerEntry, Order, Position, Trade } from "@/lib/types";
import { MatchingRunForm } from "./matching-run-form";
import { OrderForm } from "./order-form";
import { PriceChart } from "./price-chart";
import { CashLedgerTable, OrderTable, PositionTable, TradeTable } from "./trading-tables";

export function TradePage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [symbol, setSymbol] = useState("");
  const [positions, setPositions] = useState<Position[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [cashLedger, setCashLedger] = useState<CashLedgerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadAccountData(accountId: number, clearExisting = false) {
    if (!accountId) {
      return;
    }
    setError(null);
    if (clearExisting) {
      setPositions([]);
      setOrders([]);
      setTrades([]);
      setCashLedger([]);
    }
    const [nextPositions, nextOrders, nextTrades, nextCashLedger] = await Promise.allSettled([
      listPositions(accountId),
      listOrders(accountId),
      listTrades(accountId),
      listCashLedger(accountId)
    ]);

    if (nextPositions.status === "fulfilled") {
      setPositions(nextPositions.value);
    }
    if (nextOrders.status === "fulfilled") {
      setOrders(nextOrders.value);
    }
    if (nextTrades.status === "fulfilled") {
      setTrades(nextTrades.value);
    }
    if (nextCashLedger.status === "fulfilled") {
      setCashLedger(nextCashLedger.value);
    }

    const failed = [nextPositions, nextOrders, nextTrades, nextCashLedger].find((result) => result.status === "rejected");
    if (failed?.status === "rejected") {
      setError(failed.reason instanceof Error ? failed.reason.message : "Some trading panels failed to load");
    }
  }

  async function refreshAccountData() {
    if (selectedAccountId) {
      await loadAccountData(selectedAccountId);
    }
  }

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const nextAccounts = await listAccounts();
        setAccounts(nextAccounts);
        const firstAccountId = nextAccounts[0]?.id ?? null;
        setSelectedAccountId(firstAccountId);
        if (firstAccountId) {
          await loadAccountData(firstAccountId, true);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load trading data");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  async function onCancel(orderId: number) {
    try {
      await cancelOrder(orderId);
      await refreshAccountData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel order");
    }
  }

  return (
    <section className="page">
      <div className="page__header">
        <div>
          <h1>Trade</h1>
          <p className="muted">Submit limit orders, run daily matching, and inspect account state.</p>
        </div>
        <label>
          Account
          <select
            value={selectedAccountId ?? ""}
            onChange={(event) => {
              const accountId = Number(event.target.value);
              setSelectedAccountId(accountId);
              void loadAccountData(accountId, true);
            }}
          >
            {accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
          </select>
        </label>
      </div>
      {loading ? <div className="panel">Loading paper trading data...</div> : null}
      {!loading && accounts.length === 0 ? <div className="panel">No paper accounts yet. Create an account before trading.</div> : null}
      {error ? <ErrorBanner message={error} /> : null}
      <div className="grid grid--trade">
        <div className="grid">
          <label className="panel form">
            Chart symbol
            <input aria-label="Chart symbol" value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} />
          </label>
          <PriceChart symbol={symbol} />
        </div>
        <div className="grid">
          <OrderForm accounts={accounts} selectedAccountId={selectedAccountId} onSubmitted={() => refreshAccountData()} />
          <MatchingRunForm accountId={selectedAccountId} onCompleted={() => refreshAccountData()} />
        </div>
      </div>
      <section className="panel"><h2>Positions</h2><PositionTable positions={positions} /></section>
      <section className="panel"><h2>Orders</h2><OrderTable orders={orders} onCancel={onCancel} /></section>
      <section className="panel"><h2>Trades</h2><TradeTable trades={trades} /></section>
      <section className="panel"><h2>Cash Ledger</h2><CashLedgerTable entries={cashLedger} /></section>
    </section>
  );
}
