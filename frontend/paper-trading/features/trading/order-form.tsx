"use client";

import { useEffect, useState } from "react";
import { createOrder } from "@/lib/api-client";
import type { Account, OrderSide } from "@/lib/types";

export function OrderForm({
  accounts,
  selectedAccountId,
  onSubmitted
}: {
  accounts: Account[];
  selectedAccountId: number | null;
  onSubmitted: () => Promise<void> | void;
}) {
  const [accountId, setAccountId] = useState(selectedAccountId ?? accounts[0]?.id ?? 0);
  const [symbol, setSymbol] = useState("");
  const [side, setSide] = useState<OrderSide>("buy");
  const [quantity, setQuantity] = useState("100");
  const [limitPrice, setLimitPrice] = useState("");
  const [tradeDate, setTradeDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const numericQuantity = Number(quantity);
  const lotWarning = Number.isFinite(numericQuantity) && numericQuantity > 0 && numericQuantity % 100 !== 0;

  useEffect(() => {
    setAccountId(selectedAccountId ?? accounts[0]?.id ?? 0);
  }, [accounts, selectedAccountId]);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await createOrder(accountId, {
        symbol: symbol.trim().toUpperCase(),
        side,
        quantity: Number(quantity),
        limit_price: limitPrice,
        trade_date: tradeDate
      });
      await onSubmitted();
      setSymbol("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit order");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="form panel" onSubmit={onSubmit}>
      <h2>Limit Order</h2>
      <label>
        Account
        <select aria-label="Account" value={accountId} onChange={(event) => setAccountId(Number(event.target.value))} required>
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Symbol
        <input aria-label="Symbol" value={symbol} onChange={(event) => setSymbol(event.target.value)} required />
      </label>
      <label>
        Side
        <select aria-label="Side" value={side} onChange={(event) => setSide(event.target.value as OrderSide)}>
          <option value="buy">Buy</option>
          <option value="sell">Sell</option>
        </select>
      </label>
      <label>
        Quantity
        <input aria-label="Quantity" min="1" type="number" value={quantity} onChange={(event) => setQuantity(event.target.value)} required />
      </label>
      {lotWarning ? <p className="muted">A-share orders should use 100-share lots.</p> : null}
      <label>
        Limit price
        <input aria-label="Limit price" inputMode="decimal" value={limitPrice} onChange={(event) => setLimitPrice(event.target.value)} required />
      </label>
      <label>
        Trade date
        <input
          aria-label="Trade date"
          lang="en-ZA"
          type="date"
          value={tradeDate}
          onChange={(event) => setTradeDate(event.target.value)}
          required
        />
      </label>
      {error ? <div className="error-banner" role="alert">{error}</div> : null}
      <button className="button" disabled={submitting || accountId === 0} type="submit">
        Submit order
      </button>
    </form>
  );
}
