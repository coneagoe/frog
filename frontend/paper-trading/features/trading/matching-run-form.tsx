"use client";

import { useState } from "react";
import { createMatchingRun } from "@/lib/api-client";
import type { MatchingRun } from "@/lib/types";

export function MatchingRunForm({ accountId, onCompleted }: { accountId: number | null; onCompleted: () => Promise<void> | void }) {
  const [tradeDate, setTradeDate] = useState("");
  const [run, setRun] = useState<MatchingRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const nextRun = await createMatchingRun({ trade_date: tradeDate, account_id: accountId ?? undefined });
      setRun(nextRun);
      await onCompleted();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run matching");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="form panel" onSubmit={onSubmit}>
      <h2>Matching Run</h2>
      <label>
        Trade date
        <input aria-label="Matching trade date" type="date" value={tradeDate} onChange={(event) => setTradeDate(event.target.value)} required />
      </label>
      {error ? <div className="error-banner" role="alert">{error}</div> : null}
      {run ? (
        <p className="muted">
          Processed {run.processed_count}, filled {run.filled_count}, skipped {run.skipped_count}, rejected {run.rejected_count}, failed {run.failed_count}.
        </p>
      ) : null}
      <button className="button" disabled={submitting} type="submit">
        Run matching
      </button>
    </form>
  );
}
