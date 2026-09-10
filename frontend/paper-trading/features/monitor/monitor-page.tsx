"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorBanner } from "@/components/error-banner";
import { createMonitorTarget, deleteMonitorTarget, getMonitorTargetHealth, listMonitorTargets, setMonitorTargetEnabled, updateMonitorTarget } from "@/lib/api-client";
import type { CreateMonitorTargetInput, ListMonitorTargetsParams, MonitorCondition, MonitorTarget, MonitorTargetHealthPage, MonitorTargetPage } from "@/lib/types";
import { MonitorHealthPanel } from "./monitor-health-panel";
import { MonitorTargetFormModal } from "./monitor-target-form-modal";
import { MonitorTargetTable } from "./monitor-target-table";
import { TargetOperationGuard } from "./target-operation-guard";

const PAGE_SIZE = 50;

export function MonitorPage() {
  const [manualPage, setManualPage] = useState(1);
  const [manualTargets, setManualTargets] = useState<MonitorTargetPage | null>(null);
  const [healthPage, setHealthPage] = useState(1);
  const [health, setHealth] = useState<MonitorTargetHealthPage | null>(null);
  const [filters, setFilters] = useState<ListMonitorTargetsParams>({});
  const [loading, setLoading] = useState(true);
  const [healthLoading, setHealthLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [managementMode, setManagementMode] = useState(false);
  const [editing, setEditing] = useState<MonitorTarget | null | undefined>(undefined);
  const [busyTargetIds, setBusyTargetIds] = useState<Set<number>>(new Set());
  const targetOperations = useRef(new TargetOperationGuard());
  const manualRequestId = useRef(0);
  const healthRequestId = useRef(0);

  const loadManualTargets = useCallback(async (nextFilters = filters, nextPage = manualPage) => {
    const id = ++manualRequestId.current;
    setLoading(true);
    try {
      const next = await listMonitorTargets({ ...nextFilters, page: nextPage, page_size: PAGE_SIZE });
      if (id === manualRequestId.current) {
        setManualTargets(next);
        setError(null);
        if (next.page !== nextPage) setManualPage(next.page);
      }
    } catch (err) {
      if (id === manualRequestId.current) setError(err instanceof Error ? err.message : "Failed to load monitor targets");
    } finally {
      if (id === manualRequestId.current) setLoading(false);
    }
  }, [filters, manualPage]);

  const loadHealth = useCallback(async (nextPage = healthPage) => {
    const id = ++healthRequestId.current;
    setHealthLoading(true);
    try {
      const next = await getMonitorTargetHealth({ page: nextPage, page_size: PAGE_SIZE });
      if (id === healthRequestId.current) {
        setHealth(next);
        setHealthError(null);
        if (next.page !== nextPage) setHealthPage(next.page);
      }
    } catch (err) {
      if (id === healthRequestId.current) setHealthError(err instanceof Error ? err.message : "Failed to load operational health");
    } finally {
      if (id === healthRequestId.current) setHealthLoading(false);
    }
  }, [healthPage]);

  const refreshAll = useCallback(async () => { await Promise.allSettled([loadManualTargets(), loadHealth()]); }, [loadHealth, loadManualTargets]);

  useEffect(() => { void loadManualTargets(); }, [loadManualTargets]);
  useEffect(() => { void loadHealth(); }, [loadHealth]);

  function setFilter<K extends keyof ListMonitorTargetsParams>(key: K, value: ListMonitorTargetsParams[K] | undefined) {
    setManualPage(1);
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function toggleManagementMode() {
    setManagementMode((current) => {
      if (current) setEditing(undefined);
      return !current;
    });
  }

  function beginTargetOperation(targetId: number) {
    if (!targetOperations.current.begin(targetId)) return false;
    setBusyTargetIds((current) => new Set(current).add(targetId));
    return true;
  }

  function finishTargetOperation(targetId: number) {
    targetOperations.current.finish(targetId);
    setBusyTargetIds((current) => { const next = new Set(current); next.delete(targetId); return next; });
  }

  async function save(input: CreateMonitorTargetInput) {
    const targetId = editing?.id;
    if (targetId !== undefined && !beginTargetOperation(targetId)) return;
    try {
      if (editing) await updateMonitorTarget(editing.id, input); else await createMonitorTarget(input);
      setEditing(undefined);
      await refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save monitor target");
      throw err;
    } finally {
      if (targetId !== undefined) finishTargetOperation(targetId);
    }
  }

  async function toggle(target: MonitorTarget) {
    if (!beginTargetOperation(target.id)) return;
    setError(null);
    try { await setMonitorTargetEnabled(target.id, !target.enabled); await refreshAll(); } catch (err) { setError(err instanceof Error ? err.message : "Failed to update monitor target"); } finally { finishTargetOperation(target.id); }
  }

  async function remove(target: MonitorTarget) {
    if (!window.confirm(`Permanently delete monitor target ${target.stock_code}?`) || !beginTargetOperation(target.id)) return;
    setError(null);
    try { await deleteMonitorTarget(target.id); await refreshAll(); } catch (err) { setError(err instanceof Error ? err.message : "Failed to delete monitor target"); } finally { finishTargetOperation(target.id); }
  }

  return <section className="page monitor-page"><div className="page__header"><div><p className="monitor-eyebrow">Shared manual targets</p><h1>Monitor console</h1><p className="muted">Maintain the shared target list used for manual market monitoring.</p></div><div className="actions"><button className="button button--secondary" type="button" onClick={() => void refreshAll()}>Refresh targets</button><button aria-pressed={managementMode} className="button button--secondary" type="button" onClick={toggleManagementMode}>{managementMode ? "Exit management mode" : "Enter management mode"}</button>{managementMode ? <button className="button" type="button" onClick={() => setEditing(null)}>Create target</button> : null}</div></div><MonitorHealthPanel error={healthError} health={health} loading={healthLoading} onNextPage={() => setHealthPage((current) => Math.min(current + 1, health?.total_pages ?? 1))} onPreviousPage={() => setHealthPage((current) => Math.max(1, current - 1))} />{error ? <ErrorBanner message={error} /> : null}<section className="panel"><div className="monitor-filter-bar" aria-label="Monitor target filters"><label>Market<select aria-label="Market filter" value={filters.market ?? ""} onChange={(event) => setFilter("market", (event.target.value || undefined) as "A" | "HK" | "ETF" | undefined)}><option value="">All markets</option><option value="A">A-share</option><option value="HK">Hong Kong</option><option value="ETF">ETF</option></select></label><label>Frequency<select aria-label="Frequency filter" value={filters.frequency ?? ""} onChange={(event) => setFilter("frequency", (event.target.value || undefined) as "daily" | "intraday" | undefined)}><option value="">All frequencies</option><option value="daily">Daily</option><option value="intraday">Intraday</option></select></label><label>Status<select aria-label="Status filter" value={filters.enabled === undefined ? "" : String(filters.enabled)} onChange={(event) => setFilter("enabled", event.target.value === "" ? undefined : event.target.value === "true")}><option value="">All statuses</option><option value="true">Enabled</option><option value="false">Disabled</option></select></label><label>Condition<select aria-label="Condition filter" value={filters.condition_type ?? ""} onChange={(event) => setFilter("condition_type", (event.target.value || undefined) as MonitorCondition["type"] | undefined)}><option value="">All conditions</option><option value="price_threshold">Price threshold</option><option value="ma_cross">MA cross</option><option value="change_pct">Change percent</option><option value="price_cross_ma">Price cross MA</option><option value="close_cross_ma">Close cross MA</option><option value="rsi">RSI</option></select></label></div>{loading && manualTargets === null ? <p className="monitor-loading">Loading manual targets…</p> : <MonitorTargetTable busyTargetIds={busyTargetIds} loading={loading} managementMode={managementMode} page={manualPage} targets={manualTargets?.items ?? []} totalCount={manualTargets?.total_count ?? 0} totalPages={manualTargets?.total_pages ?? 0} onNextPage={() => setManualPage((current) => Math.min(current + 1, manualTargets?.total_pages ?? 1))} onPreviousPage={() => setManualPage((current) => Math.max(1, current - 1))} {...(managementMode ? { onEdit: setEditing, onToggle: toggle, onDelete: remove } : {})} />}</section><MonitorTargetFormModal open={editing !== undefined} target={editing ?? null} onClose={() => setEditing(undefined)} onSubmit={save} /></section>;
}
