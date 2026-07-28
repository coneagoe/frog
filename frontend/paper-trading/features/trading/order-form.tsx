"use client";

import { useEffect, useState } from "react";
import { createOrder } from "@/lib/api-client";
import type { Account, Market, OrderSide } from "@/lib/types";

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
  const [market, setMarket] = useState<Market>("a_share");
  const [quantity, setQuantity] = useState("100");
  const [limitPrice, setLimitPrice] = useState("");
  const [tradeDate, setTradeDate] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const numericQuantity = Number(quantity);
  const lotWarning = market === "a_share" && Number.isFinite(numericQuantity) && numericQuantity > 0 && numericQuantity % 100 !== 0;

  useEffect(() => {
    setAccountId(selectedAccountId ?? accounts[0]?.id ?? 0);
  }, [accounts, selectedAccountId]);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const commentTrimmed = comment.trim();
      await createOrder(accountId, {
        symbol: symbol.trim().toUpperCase(),
        side,
        market,
        quantity: Number(quantity),
        limit_price: limitPrice,
        trade_date: tradeDate,
        ...(commentTrimmed ? { comment: commentTrimmed } : {})
      });
      await onSubmitted();
      setSymbol("");
      setComment("");
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
        Market
        <select
          aria-label="Market"
          value={market}
          onChange={(event) => setMarket(event.target.value === "hk_connect" ? "hk_connect" : "a_share")}
        >
          <option value="a_share">A-share</option>
          <option value="hk_connect">Hong Kong Connect</option>
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
      <label>
        Comment
        <input aria-label="Comment" value={comment} onChange={(event) => setComment(event.target.value)} />
      </label>
      {error ? <div className="error-banner" role="alert">{error}</div> : null}
      <button className="button" disabled={submitting || accountId === 0} type="submit">
        Submit order
      </button>
    </form>
  );
}
