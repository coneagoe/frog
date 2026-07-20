"use client";

import { useEffect, useRef } from "react";
import { createChart, LineSeries } from "lightweight-charts";
import { EmptyState } from "@/components/empty-state";
import type { Snapshot } from "@/lib/types";

export function AssetChart({ snapshots }: { snapshots: Snapshot[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!containerRef.current || snapshots.length === 0) {
      return;
    }
    const chart = createChart(containerRef.current, {
      height: 320,
      layout: { textColor: "#d6e0f0", background: { color: "#111827" } }
    });
    const series = chart.addSeries(LineSeries, { color: "#38bdf8" });
    series.setData(
      snapshots.map((snapshot) => ({
        time: snapshot.trade_date,
        value: Number(snapshot.net_asset_value ?? snapshot.total_assets)
      }))
    );
    return () => chart.remove();
  }, [snapshots]);

  if (snapshots.length === 0) {
    return <EmptyState title="No snapshots yet" description="Run matching to generate account valuation snapshots." />;
  }

  return <div ref={containerRef} />;
}
