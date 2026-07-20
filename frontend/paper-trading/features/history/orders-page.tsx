"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ErrorBanner } from "@/components/error-banner";
import { cancelOrder, deleteOrder, listAccounts, listOrders, updateOrderComment } from "@/lib/api-client";
import type { Account, Order } from "@/lib/types";
import { OrderTable } from "@/features/trading/trading-tables";

export function OrdersPage() {
  const searchParams = useSearchParams();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingOrderId, setEditingOrderId] = useState<number | null>(null);
  const [editingValue, setEditingValue] = useState("");
  const [deletingOrderId, setDeletingOrderId] = useState<number | null>(null);
  const requestIdRef = useRef(0);

  async function loadOrders(accountId: number) {
    const requestId = ++requestIdRef.current;
    setOrders([]);
    setError(null);
    try {
      const nextOrders = await listOrders(accountId);
      if (requestId === requestIdRef.current) {
        setOrders(nextOrders);
      }
    } catch (err) {
      if (requestId === requestIdRef.current) {
        setError(err instanceof Error ? err.message : "Failed to load orders");
      }
    }
  }

  function handleEditStart(orderId: number) {
    const order = orders.find((o) => o.id === orderId);
    setEditingOrderId(orderId);
    setEditingValue(order?.comment ?? "");
  }

  function handleEditCancel() {
    setEditingOrderId(null);
    setEditingValue("");
  }

  async function handleEditSave(orderId: number) {
    const requestId = ++requestIdRef.current;
    setError(null);
    try {
      const updatedOrder = await updateOrderComment(orderId, editingValue);
      if (requestId === requestIdRef.current) {
        setOrders((prev) => prev.map((o) => (o.id === orderId ? updatedOrder : o)));
        setEditingOrderId(null);
        setEditingValue("");
      }
    } catch (err) {
      if (requestId === requestIdRef.current) {
        setError(err instanceof Error ? err.message : "Failed to update comment");
      }
    }
  }

  async function handleCancel(orderId: number) {
    const requestId = ++requestIdRef.current;
    setError(null);
    try {
      await cancelOrder(orderId);
      if (requestId === requestIdRef.current && selectedAccountId) {
        await loadOrders(selectedAccountId);
      }
    } catch (err) {
      if (requestId === requestIdRef.current) {
        setError(err instanceof Error ? err.message : "Failed to cancel order");
      }
    }
  }

  async function handleDelete(orderId: number) {
    const confirmed = window.confirm(
      "Delete this order? Filled trades, cash ledger, positions, and snapshots for this paper account will be recalculated."
    );
    if (!confirmed) return;

    const requestId = ++requestIdRef.current;
    setDeletingOrderId(orderId);
    setError(null);
    try {
      await deleteOrder(orderId);
      if (requestId === requestIdRef.current && selectedAccountId) {
        await loadOrders(selectedAccountId);
      }
    } catch (err) {
      if (requestId === requestIdRef.current) {
        setError(err instanceof Error ? err.message : "Failed to delete order");
      }
    } finally {
      setDeletingOrderId((current) => (current === orderId ? null : current));
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const nextAccounts = await listAccounts();
        if (cancelled) return;
        setAccounts(nextAccounts);
        const requestedAccountId = Number(searchParams.get("accountId"));
        const firstAccountId = nextAccounts.some((account) => account.id === requestedAccountId)
          ? requestedAccountId
          : nextAccounts[0]?.id ?? null;
        setSelectedAccountId(firstAccountId);
        if (firstAccountId) {
          await loadOrders(firstAccountId);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load orders data");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [searchParams]);

  return (
    <section className="page">
      <div className="page__header">
        <div>
          <h1>Orders</h1>
          <p className="muted">Review and cancel historical paper orders.</p>
        </div>
        <label>
          <span className="account-selector">
            Account
            <select
              disabled={accounts.length === 0}
              value={selectedAccountId ?? ""}
              onChange={(event) => {
                const accountId = Number(event.target.value);
                setSelectedAccountId(accountId);
                void loadOrders(accountId);
              }}
            >
              {accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
            </select>
          </span>
        </label>
      </div>
      {loading ? <div className="panel">Loading orders...</div> : null}
      {!loading && accounts.length === 0 ? <div className="panel">No paper accounts yet. Create an account before viewing orders.</div> : null}
      {error ? <ErrorBanner message={error} /> : null}
      <OrderTable
        orders={orders}
        onCancel={handleCancel}
        onDelete={handleDelete}
        deletingOrderId={deletingOrderId}
        editingOrderId={editingOrderId}
        editingValue={editingValue}
        onEditStart={handleEditStart}
        onEditValueChange={setEditingValue}
        onEditSave={handleEditSave}
        onEditCancel={handleEditCancel}
      />
    </section>
  );
}
