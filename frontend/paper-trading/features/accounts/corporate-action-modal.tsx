"use client";

import { useEffect, useRef, useState } from "react";
import { ErrorBanner } from "@/components/error-banner";
import { createCorporateAction } from "@/lib/api-client";
import type { Account, CorporateActionInput, CorporateActionResult, CorporateActionType, Market } from "@/lib/types";

type Props = {
  account: Account | null;
  open: boolean;
  onClose: () => void;
  onCompleted: (result: CorporateActionResult) => Promise<void> | void;
};
const modes: { value: CorporateActionType; label: string }[] = [
  { value: "dividend", label: "Dividend" },
  { value: "split", label: "Stock split" },
  { value: "reverse_split", label: "Reverse split" },
  { value: "bonus_share", label: "Bonus shares" },
  { value: "rights_issue", label: "Rights issue" }
];

const initialEventAt = () => new Date().toISOString().replace(".000Z", "Z");
function isMarket(value: string): value is Market {
  return value === "a_share" || value === "hk_connect" || value === "etf";
}

export function CorporateActionModal({ account, open, onClose, onCompleted }: Props) {
  const [symbol, setSymbol] = useState("");
  const [market, setMarket] = useState<Market>("a_share");
  const [eventType, setEventType] = useState<CorporateActionType>("dividend");
  const [eventAt, setEventAt] = useState(initialEventAt);
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const [firstValue, setFirstValue] = useState("");
  const [secondValue, setSecondValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const submissionAccountIdRef = useRef<number | null>(null);
  const currentAccountIdRef = useRef<number | null>(account?.id ?? null);
  currentAccountIdRef.current = account?.id ?? null;

  useEffect(() => {
    if (open) {
      restoreFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      setSymbol(""); setMarket("a_share"); setEventType("dividend"); setEventAt(initialEventAt());
      setIdempotencyKey(""); setFirstValue(""); setSecondValue(""); setError(null); setSubmitting(false);
      requestAnimationFrame(() => {
        const firstControl = dialogRef.current?.querySelector<HTMLElement>("input, select, textarea, button");
        firstControl?.focus();
      });
      return () => {
        restoreFocusRef.current?.focus();
        restoreFocusRef.current = null;
      };
    }
  }, [open]);

  if (!open || !account) return null;

  const firstLabel = eventType === "dividend" ? "Per-share amount" : eventType === "bonus_share" ? "Bonus ratio" : eventType === "rights_issue" ? "Subscription ratio" : "Ratio";
  const positive = (value: string) => value.trim() !== "" && Number.isFinite(Number(value)) && Number(value) > 0;
  const validate = (): string | null => {
    if (!symbol.trim()) return "Symbol is required";
    if (!eventAt.trim() || !/[zZ]|[+-]\d\d:\d\d$/.test(eventAt.trim()) || !Number.isFinite(new Date(eventAt).getTime())) return "Event time must be a valid timezone-aware ISO timestamp";
    if (!idempotencyKey.trim()) return "Idempotency key is required";
    if (!positive(firstValue)) return `${firstLabel} must be greater than 0 and finite`;
    if (eventType === "reverse_split" && Number(firstValue) >= 1) return "Reverse split ratio must be below 1";
    if (eventType === "rights_issue" && !positive(secondValue)) return "Subscription price must be greater than 0 and finite";
    return null;
  };

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const validationError = validate();
    if (validationError) { setError(validationError); return; }
    setSubmitting(true); setError(null);
    const currentAccount = account;
    if (!currentAccount) {
      setSubmitting(false);
      return;
    }
    submissionAccountIdRef.current = currentAccount.id;
    const parameters = eventType === "dividend" ? { per_share_amount: firstValue } : eventType === "bonus_share" ? { bonus_ratio: firstValue } : eventType === "rights_issue" ? { subscription_ratio: firstValue, subscription_price: secondValue } : { ratio: firstValue };
    const input: CorporateActionInput = { symbol: symbol.trim(), market, event_type: eventType, event_at: eventAt.trim(), idempotency_key: idempotencyKey.trim(), parameters };
    try {
      const result = await createCorporateAction(currentAccount.id, input);
      await onCompleted(result);
      if (currentAccountIdRef.current === submissionAccountIdRef.current) onClose();
    }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to apply corporate action"); }
    finally {
      setSubmitting(false);
      submissionAccountIdRef.current = null;
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      if (!submitting) onClose();
      return;
    }
    if (event.key !== "Tab" || !dialogRef.current) return;
    const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(
      "button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex=\"-1\"])"
    ));
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div className="modal-backdrop" data-testid="corporate-action-backdrop" onClick={() => { if (!submitting) onClose(); }}>
      <div
        className="modal"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={handleKeyDown}
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={`Corporate action for ${account.name}`}
      >
        <div className="modal__header"><div><p className="muted">Account: {account.name}</p><h2>Apply corporate action</h2></div></div>
        <form onSubmit={onSubmit}>
          <div className="modal__body">
            {eventType === "rights_issue" ? <p className="muted" role="note">Rights issues use available cash. Available cash: {account.cash_available}. Subscription cash will be checked before processing.</p> : null}
            {error ? <ErrorBanner message={error} /> : null}
            <div className="form">
              <label>Symbol<input aria-label="Symbol" value={symbol} onChange={(e) => setSymbol(e.target.value)} /></label>
              <label>Action type<select aria-label="Action type" value={eventType} onChange={(e) => { setEventType(e.target.value as CorporateActionType); setFirstValue(""); setSecondValue(""); }} >{modes.map((mode) => <option key={mode.value} value={mode.value}>{mode.label}</option>)}</select></label>
              <label>Market<select aria-label="Market" value={market} onChange={(e) => { if (isMarket(e.target.value)) setMarket(e.target.value); }}><option value="a_share">A-share</option><option value="hk_connect">Hong Kong Connect</option><option value="etf">ETF</option></select></label>
              <label>Event time (ISO with timezone)<input aria-label="Event time" value={eventAt} onChange={(e) => setEventAt(e.target.value)} /></label>
              <label>Idempotency key<input aria-label="Idempotency key" value={idempotencyKey} onChange={(e) => setIdempotencyKey(e.target.value)} /></label>
              <label>{firstLabel}<input aria-label={firstLabel} inputMode="decimal" value={firstValue} onChange={(e) => setFirstValue(e.target.value)} /></label>
              {eventType === "rights_issue" ? <label>Subscription price<input aria-label="Subscription price" inputMode="decimal" value={secondValue} onChange={(e) => setSecondValue(e.target.value)} /></label> : null}
            </div>
          </div>
          <div className="modal__footer"><button className="button button--secondary" disabled={submitting} type="button" onClick={onClose}>Cancel</button><button className="button" disabled={submitting} type="submit">{submitting ? "Applying…" : "Apply action"}</button></div>
        </form>
      </div>
    </div>
  );
}
