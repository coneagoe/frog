"use client";

import { useEffect, useState } from "react";
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

  useEffect(() => {
    if (open && account) {
      setRows([emptyRow()]);
      setError(null);
      setSubmitting(false);
    }
  }, [account, open]);

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
    if (rows.length <= 1) return;
    setError(null);
    setRows((current) => current.filter((_, i) => i !== index));
  }

  const rowSummary = `${rows.length} ${rows.length === 1 ? "row" : "rows"} ready for input`;

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
      if (row.cost_price.trim() === "" || Number.isNaN(price) || price < 0) {
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
        if (err.message.toLowerCase().includes("already has positions")) {
          setError("This account already has positions. Import is only available for empty accounts.");
        } else {
          setError(err.message);
        }
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
        className="modal import-modal"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={"Import initial positions for " + account.name}
      >
        <div className="modal__header import-modal__header">
          <div>
            <p className="import-modal__eyebrow">Account: {account.name}</p>
            <h2>Import initial positions</h2>
            <p className="import-modal__intro">Set starting holdings for this account. Cash will not change.</p>
          </div>
        </div>
        <form onSubmit={onSubmit}>
          <div className="modal__body import-modal__body">
            <div className="import-modal__rules" aria-label="Import rules">
              <span>Use this once for an empty account.</span>
              <span>Lots with the same symbol are allowed.</span>
              <span>Importing positions does not add or remove cash.</span>
            </div>

            {error ? (
              <div role="alert" className="error-banner">
                {error}
              </div>
            ) : null}

            <div className="import-grid" data-testid="import-positions-grid">
              <div className="import-grid__header" aria-hidden="true">
                <span>Symbol</span>
                <span>Quantity</span>
                <span>Cost price</span>
                <span>Buy date</span>
                <span>Action</span>
              </div>

              {rows.map((row, index) => (
                <div className="import-grid__row" data-testid="import-position-row" key={index}>
                  <label className="import-grid__field">
                    <span>Symbol</span>
                    <input
                      aria-label="Symbol"
                      autoComplete="off"
                      placeholder="000001"
                      value={row.symbol}
                      onChange={(e) => updateRow(index, "symbol", e.target.value)}
                    />
                  </label>

                  <label className="import-grid__field">
                    <span>Quantity</span>
                    <input
                      aria-label="Quantity"
                      inputMode="numeric"
                      placeholder="100"
                      value={row.quantity}
                      onChange={(e) => updateRow(index, "quantity", e.target.value)}
                    />
                  </label>

                  <label className="import-grid__field">
                    <span>Cost price</span>
                    <input
                      aria-label="Cost price"
                      inputMode="decimal"
                      placeholder="10.23"
                      value={row.cost_price}
                      onChange={(e) => updateRow(index, "cost_price", e.target.value)}
                    />
                  </label>

                  <label className="import-grid__field">
                    <span>Buy date</span>
                    <input
                      aria-label="Buy trade date"
                      inputMode="numeric"
                      placeholder="YYYY-MM-DD"
                      value={row.buy_trade_date}
                      onChange={(e) => updateRow(index, "buy_trade_date", e.target.value)}
                    />
                    <small>YYYY-MM-DD</small>
                  </label>

                  <div className="import-grid__action">
                    <button type="button" aria-label="Remove row" onClick={() => removeRow(index)}>
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <div className="import-modal__grid-actions">
              <button className="button button--secondary" type="button" onClick={addRow}>
                Add row
              </button>
            </div>
          </div>
          <div className="modal__footer import-modal__footer">
            <p className="import-modal__footer-note">{rowSummary}</p>
            <div className="import-modal__footer-actions">
              <button className="button button--secondary" onClick={onClose} type="button">
                Cancel
              </button>
              <button className="button" disabled={submitting} type="submit">
                {submitting ? "Importing…" : "Import positions"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
