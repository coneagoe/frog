"use client";

import { useState } from "react";
import { importPositions } from "@/lib/api-client";
import type { Account, ImportPositionsResult } from "@/lib/types";

type ImportRow = {
  symbol: string;
  quantity: string;
  cost_price: string;
  buy_trade_date: string;
};

function emptyRow(): ImportRow {
  return { symbol: "", quantity: "", cost_price: "", buy_trade_date: "" };
}

type ImportPositionsModalProps = {
  account: Account | null;
  open: boolean;
  onClose: () => void;
  onImported: (result: ImportPositionsResult) => Promise<void> | void;
};

export function ImportPositionsModal({ account, open, onClose, onImported }: ImportPositionsModalProps) {
  const [rows, setRows] = useState<ImportRow[]>([emptyRow()]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!account || !open) {
    return null;
  }

  function updateRow(index: number, field: keyof ImportRow, value: string) {
    setError(null);
    setRows((current) => {
      const next = current.map((r) => ({ ...r }));
      next[index][field] = value;
      return next;
    });
  }

  function addRow() {
    setError(null);
    setRows((current) => [...current, emptyRow()]);
  }

  function removeRow(index: number) {
    setError(null);
    setRows((current) => current.filter((_, i) => i !== index));
  }

  function validate(): string | null {
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      if (row.symbol.trim() === "") {
        return `Row ${i + 1}: Symbol is required`;
      }
      const qty = Number(row.quantity);
      if (!Number.isInteger(qty) || qty <= 0) {
        return `Row ${i + 1}: Quantity must be a whole number greater than 0`;
      }
      const price = Number(row.cost_price);
      if (Number.isNaN(price) || price < 0) {
        return `Row ${i + 1}: Cost price must be a non-negative number`;
      }
      if (!/^\d{4}-\d{2}-\d{2}$/.test(row.buy_trade_date)) {
        return `Row ${i + 1}: Buy trade date must be in YYYY-MM-DD format`;
      }
    }
    return null;
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();

    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const result = await importPositions(account!.id, {
        positions: rows.map((r) => ({
          symbol: r.symbol.trim(),
          quantity: Number(r.quantity),
          cost_price: r.cost_price,
          buy_trade_date: r.buy_trade_date
        }))
      });
      await onImported(result);
      onClose();
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to import positions");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={"Import positions for " + account.name}
      >
        <div className="modal__header">
          <h2>Import positions — {account.name}</h2>
        </div>
        <form onSubmit={onSubmit}>
          <div className="modal__body">
            <table className="form">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Quantity</th>
                  <th>Cost price</th>
                  <th>Buy trade date</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={index}>
                    <td>
                      <input
                        aria-label="Symbol"
                        value={row.symbol}
                        onChange={(e) => updateRow(index, "symbol", e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        aria-label="Quantity"
                        inputMode="numeric"
                        value={row.quantity}
                        onChange={(e) => updateRow(index, "quantity", e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        aria-label="Cost price"
                        inputMode="decimal"
                        value={row.cost_price}
                        onChange={(e) => updateRow(index, "cost_price", e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        aria-label="Buy trade date"
                        value={row.buy_trade_date}
                        onChange={(e) => updateRow(index, "buy_trade_date", e.target.value)}
                      />
                    </td>
                    <td>
                      <button type="button" aria-label="Remove row" onClick={() => removeRow(index)}>
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <button type="button" onClick={addRow}>
              Add row
            </button>
            <p className="modal__note">
              Importing initializes existing holdings only and does not change cash.
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
              {submitting ? "Importing…" : "Import positions"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
