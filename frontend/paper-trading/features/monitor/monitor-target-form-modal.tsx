"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api-error";
import type { CreateMonitorTargetInput, MonitorCondition, MonitorTarget } from "@/lib/types";
import { ConditionEditor } from "./condition-editor";

type Props = { open: boolean; target: MonitorTarget | null; onClose: () => void; onSubmit: (input: CreateMonitorTargetInput) => Promise<void> | void };
type FieldErrors = Record<string, string>;
const defaultCondition: MonitorCondition = { type: "price_threshold", direction: "above", value: 1 };

function validate(stockCode: string, market: CreateMonitorTargetInput["market"], frequency: "daily" | "intraday", condition: MonitorCondition): FieldErrors {
  const errors: FieldErrors = {};
  if (!stockCode) errors.stock_code = "Stock code is required.";
  else if (market === "A" && !/^\d{6}$/.test(stockCode)) errors.stock_code = "Enter a valid 6-digit A-share code.";
  const validPositive = (value: number) => Number.isFinite(value) && value > 0;
  if ("value" in condition && !validPositive(condition.value)) errors["condition.value"] = "Enter a number greater than 0.";
  if ("period" in condition && condition.period !== undefined && !validPositive(condition.period)) errors["condition.period"] = "Enter a whole number greater than 0.";
  if (condition.type === "ma_cross") {
    if (!validPositive(condition.fast)) errors["condition.fast"] = "Enter a whole number greater than 0.";
    if (!validPositive(condition.slow)) errors["condition.slow"] = "Enter a whole number greater than 0.";
    if (validPositive(condition.fast) && validPositive(condition.slow) && condition.fast >= condition.slow) errors["condition.ma_cross"] = "Fast period must be less than slow period.";
  }
  if (condition.type === "rsi" && (condition.value < 0 || condition.value > 100 || !Number.isFinite(condition.value))) errors["condition.value"] = "RSI value must be between 0 and 100.";
  if (condition.type === "close_cross_ma" && (market !== "A" || frequency !== "daily")) errors.condition = "Close crosses MA is available for daily A-share targets only";
  return errors;
}

function apiFieldErrors(error: unknown): FieldErrors {
  if (!(error instanceof ApiError) || !error.details || typeof error.details !== "object" || Array.isArray(error.details)) return {};
  const details = error.details as { field?: unknown; message?: unknown };
  if (typeof details.field !== "string" || typeof details.message !== "string") return {};
  return { [details.field.startsWith("condition.") ? details.field : details.field]: details.message };
}

export function MonitorTargetFormModal({ open, target, onClose, onSubmit }: Props) {
  const [stockCode, setStockCode] = useState(""); const [market, setMarket] = useState<CreateMonitorTargetInput["market"]>("A"); const [frequency, setFrequency] = useState<"daily" | "intraday">("daily"); const [resetMode, setResetMode] = useState<"auto" | "manual">("auto"); const [enabled, setEnabled] = useState(true); const [note, setNote] = useState(""); const [condition, setCondition] = useState<MonitorCondition>(defaultCondition); const [error, setError] = useState<string | null>(null); const [fieldErrors, setFieldErrors] = useState<FieldErrors>({}); const [saving, setSaving] = useState(false); const dialogRef = useRef<HTMLDivElement | null>(null); const restoreFocusRef = useRef<HTMLElement | null>(null);
  useEffect(() => { if (open) { restoreFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; setStockCode(target?.stock_code ?? ""); setMarket(target?.market ?? "A"); setFrequency(target?.frequency ?? "daily"); setResetMode(target?.reset_mode ?? "auto"); setEnabled(target?.enabled ?? true); setNote(target?.note ?? ""); setCondition(target?.condition ?? defaultCondition); setError(null); setFieldErrors({}); setSaving(false); requestAnimationFrame(() => dialogRef.current?.querySelector<HTMLElement>("input, select, textarea")?.focus()); return () => { restoreFocusRef.current?.focus(); restoreFocusRef.current = null; }; } }, [open, target]);
  if (!open) return null;
  async function submit(event: React.FormEvent) { event.preventDefault(); const validation = validate(stockCode.trim(), market, frequency, condition); if (Object.keys(validation).length) { setFieldErrors(validation); setError(validation.condition ?? null); return; } setSaving(true); setError(null); setFieldErrors({}); try { await onSubmit({ stock_code: stockCode.trim(), market, frequency, reset_mode: resetMode, enabled, note: note.trim() || null, condition }); } catch (err) { const nextFieldErrors = apiFieldErrors(err); setFieldErrors(nextFieldErrors); setError(Object.keys(nextFieldErrors).length ? null : err instanceof Error ? err.message : "Failed to save monitor target"); } finally { setSaving(false); } }
  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) { if (event.key === "Escape") { if (!saving) onClose(); return; } if (event.key !== "Tab" || !dialogRef.current) return; const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>("button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex=\"-1\"])")); if (!focusable.length) return; const first = focusable[0]; const last = focusable[focusable.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } }
  const close = () => { if (!saving) onClose(); };
  return <div className="monitor-editor-backdrop" onClick={close}><div className="monitor-editor-panel" ref={dialogRef} role="dialog" aria-modal="true" aria-label={target ? "Edit monitor target" : "Create monitor target"} onClick={(event) => event.stopPropagation()} onKeyDown={handleKeyDown}><div className="modal__header"><h2>{target ? "Edit monitor target" : "Create monitor target"}</h2><button aria-label="Close editor" className="monitor-editor-close" disabled={saving} type="button" onClick={close}>×</button></div><form onSubmit={submit}><div className="modal__body form"><label>Stock code<input aria-label="Stock code" aria-invalid={Boolean(fieldErrors.stock_code)} aria-describedby={fieldErrors.stock_code ? "stock-code-error" : undefined} required value={stockCode} onChange={(event) => setStockCode(event.target.value)} />{fieldErrors.stock_code ? <span className="field-error" id="stock-code-error" role="alert">{fieldErrors.stock_code}</span> : null}</label><div className="monitor-form-grid"><label>Market<select aria-label="Market" value={market} onChange={(event) => setMarket(event.target.value as CreateMonitorTargetInput["market"])}><option value="A">A-share</option><option value="HK">Hong Kong</option><option value="ETF">ETF</option></select></label><label>Frequency<select aria-label="Frequency" value={frequency} onChange={(event) => setFrequency(event.target.value as "daily" | "intraday")}><option value="daily">Daily</option><option value="intraday">Intraday</option></select></label></div><ConditionEditor condition={condition} errors={fieldErrors} market={market} frequency={frequency} onChange={setCondition} /><label>Note<input aria-label="Note" value={note} onChange={(event) => setNote(event.target.value)} /></label><div className="monitor-form-grid"><label>Reset mode<select aria-label="Reset mode" value={resetMode} onChange={(event) => setResetMode(event.target.value as "auto" | "manual")}><option value="auto">Automatic</option><option value="manual">Manual</option></select></label><label className="monitor-enabled"><input aria-label="Enabled" type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} /> Enabled</label></div>{error ? <div className="error-banner" role="alert">{error}</div> : null}</div><div className="modal__footer"><button className="button button--secondary" disabled={saving} type="button" onClick={close}>Cancel</button><button className="button" disabled={saving} type="submit">{saving ? "Saving…" : target ? "Save changes" : "Create target"}</button></div></form></div></div>;
}
