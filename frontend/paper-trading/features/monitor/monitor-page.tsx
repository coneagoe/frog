"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorBanner } from "@/components/error-banner";
import {
  createMonitorTarget,
  deleteMonitorTarget,
  listMonitorTargets,
  setMonitorTargetEnabled,
  updateMonitorTarget,
} from "@/lib/api-client";
import type {
  CreateMonitorTargetInput,
  ListMonitorTargetsParams,
  MonitorTarget,
  UnifiedMonitorTargetPage,
} from "@/lib/types";
import { MonitorTargetFormModal } from "./monitor-target-form-modal";
import { MonitorTargetTable } from "./monitor-target-table";
import { TargetOperationGuard } from "./target-operation-guard";

const DEFAULT_SIZE = 50;
const emptyFilters: ListMonitorTargetsParams = {};

export function MonitorPage() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_SIZE);
  const [filters, setFilters] = useState<ListMonitorTargetsParams>(emptyFilters);
  const [sort, setSort] = useState<"default" | "stock_code_asc" | "stock_code_desc">("default");
  const [response, setResponse] = useState<UnifiedMonitorTargetPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [managementMode, setManagementMode] = useState(false);
  const [editing, setEditing] = useState<MonitorTarget | null | undefined>(undefined);
  const [busyTargetIds, setBusyTargetIds] = useState<Set<number>>(new Set());
  const requestId = useRef(0);
  const operations = useRef(new TargetOperationGuard());

  const load = useCallback(
    async (nextPage = page) => {
      const id = ++requestId.current;
      setLoading(true);
      try {
        const next = await listMonitorTargets({
          ...filters,
          page: nextPage,
          page_size: pageSize,
          sort,
        });
        if (id !== requestId.current) return;
        setResponse(next);
        setError(null);
        if (next.pagination.page !== nextPage) setPage(next.pagination.page);
      } catch (err) {
        if (id === requestId.current) {
          setError(err instanceof Error ? err.message : "Failed to load monitor targets");
        }
      } finally {
        if (id === requestId.current) setLoading(false);
      }
    },
    [filters, page, pageSize, sort],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 250);
    return () => window.clearTimeout(timer);
  }, [load]);

  const refresh = useCallback(() => load(page), [load, page]);
  function changeFilter(key: keyof ListMonitorTargetsParams, value: string) {
    setPage(1);
    setFilters((current) => ({
      ...current,
      [key]: value === "" ? undefined : key === "enabled" ? value === "true" : value,
    }));
  }

  function clearFilters() {
    setFilters(emptyFilters);
    setPage(1);
  }

  function begin(id: number) {
    if (!operations.current.begin(id)) return false;
    setBusyTargetIds((current) => new Set(current).add(id));
    return true;
  }

  function finish(id: number) {
    operations.current.finish(id);
    setBusyTargetIds((current) => {
      const next = new Set(current);
      next.delete(id);
      return next;
    });
  }

  async function save(input: CreateMonitorTargetInput) {
    const id = editing?.id;
    if (id !== undefined && !begin(id)) return;
    try {
      if (editing) await updateMonitorTarget(id!, input);
      else await createMonitorTarget(input);
      setEditing(undefined);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save monitor target");
      throw err;
    } finally {
      if (id !== undefined) finish(id);
    }
  }

  async function toggle(target: MonitorTarget) {
    if (!begin(target.id)) return;
    try {
      await setMonitorTargetEnabled(target.id, !target.enabled);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update monitor target");
    } finally {
      finish(target.id);
    }
  }

  async function remove(target: MonitorTarget) {
    if (!window.confirm(`Permanently delete monitor target ${target.stock_code}?`) || !begin(target.id)) return;
    try {
      await deleteMonitorTarget(target.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete monitor target");
    } finally {
      finish(target.id);
    }
  }

  const pagination = response?.pagination;
  const queryDisabled = loading;

  return (
    <section className="page monitor-page">
      <div className="page__header">
        <div>
          <p className="monitor-eyebrow">Unified monitor targets</p>
          <h1>Monitor console</h1>
          <p className="muted">View manual and workflow monitor targets.</p>
        </div>
        <div className="actions">
          <button className="button button--secondary" disabled={queryDisabled} type="button" onClick={() => void refresh()}>
            Refresh targets
          </button>
          <button
            aria-pressed={managementMode}
            className="button button--secondary"
            type="button"
            onClick={() => {
              setManagementMode((value) => !value);
              setEditing(undefined);
            }}
          >
            {managementMode ? "Exit management mode" : "Enter management mode"}
          </button>
          {managementMode ? (
            <button className="button" type="button" onClick={() => setEditing(null)}>
              Create target
            </button>
          ) : null}
        </div>
      </div>
      <section className="panel">
        <div className="monitor-filter-bar" aria-label="Monitor target filters">
          <label>
            Market
            <select aria-label="Market filter" disabled={queryDisabled} value={filters.market ?? ""} onChange={(event) => changeFilter("market", event.target.value)}>
              <option value="">All markets</option>
              <option value="A">A-share</option>
              <option value="HK">Hong Kong</option>
              <option value="ETF">ETF</option>
            </select>
          </label>
          <label>
            Frequency
            <select aria-label="Frequency filter" disabled={queryDisabled} value={filters.frequency ?? ""} onChange={(event) => changeFilter("frequency", event.target.value)}>
              <option value="">All frequencies</option>
              <option value="daily">Daily</option>
              <option value="intraday">Intraday</option>
            </select>
          </label>
          <label>
            Status
            <select aria-label="Status filter" disabled={queryDisabled} value={filters.enabled === undefined ? "" : String(filters.enabled)} onChange={(event) => changeFilter("enabled", event.target.value)}>
              <option value="">All statuses</option>
              <option value="true">Enabled</option>
              <option value="false">Disabled</option>
            </select>
          </label>
          <label>
            Condition (manual only)
            <select aria-label="Condition type filter" disabled={queryDisabled} value={filters.condition_type ?? ""} onChange={(event) => changeFilter("condition_type", event.target.value)}>
              <option value="">All conditions</option>
              <option value="price_threshold">Price threshold</option>
              <option value="rsi">RSI</option>
              <option value="ma_cross">MA cross</option>
              <option value="change_pct">Change percent</option>
              <option value="price_cross_ma">Price cross MA</option>
              <option value="close_cross_ma">Close cross MA</option>
            </select>
          </label>
          {response?.items.length !== 0 ? (
            <label>
              Page size
              <select aria-label="Page size" disabled={queryDisabled} value={pageSize} onChange={(event) => { setPage(1); setPageSize(Number(event.target.value)); }}>
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </label>
          ) : null}
          <button className="button button--secondary" disabled={queryDisabled} type="button" onClick={clearFilters}>
            Clear filters
          </button>
        </div>
      </section>
      {error ? (
        <>
          <ErrorBanner message={error} />
          <button className="button button--secondary" type="button" onClick={() => void refresh()}>
            Retry
          </button>
        </>
      ) : null}
      <div role="status" aria-live="polite">{loading ? (response ? "Refreshing…" : "Loading monitor targets…") : null}</div>
      {response ? <div className="monitor-health-summary" aria-label="Monitor summary">{Object.entries(response.summary).map(([label, value]) => <div className="monitor-health-counter" key={label}><span>{label.replaceAll("_", " ")}</span><strong>{value}</strong></div>)}</div> : null}
      {response && response.items.length === 0 ? <p className="muted">{Object.values(filters).some((value) => value !== undefined) ? "No monitor targets match the selected filters." : "No monitor targets yet."}</p> : null}
      <MonitorTargetTable
        targets={response?.items ?? []}
        busyTargetIds={busyTargetIds}
        managementMode={managementMode}
        loading={loading}
        page={pagination?.page ?? page}
        totalCount={pagination?.total_count ?? 0}
        totalPages={pagination?.total_pages ?? 0}
        sort={sort}
        onSort={() => {
          setPage(1);
          setSort(sort === "default" ? "stock_code_asc" : sort === "stock_code_asc" ? "stock_code_desc" : "default");
        }}
        onPreviousPage={() => setPage((current) => Math.max(1, current - 1))}
        onNextPage={() => setPage((current) => Math.min(pagination?.total_pages ?? current, current + 1))}
        onEdit={(target) => target.can_manage && setEditing(target)}
        onToggle={(target) => target.can_manage && void toggle(target)}
        onDelete={(target) => target.can_manage && void remove(target)}
      />
      {editing !== undefined && managementMode ? <MonitorTargetFormModal open target={editing} onClose={() => setEditing(undefined)} onSubmit={save} /> : null}
    </section>
  );
}
