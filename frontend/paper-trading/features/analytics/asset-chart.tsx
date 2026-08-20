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
      layout: { textColor: "#1f2933", background: { color: "#ffffff" } },
      grid: { vertLines: { color: "#e1e5df" }, horzLines: { color: "#e1e5df" } },
      rightPriceScale: { borderColor: "#ccd4c6" },
      timeScale: { borderColor: "#ccd4c6" }
    });
    const series = chart.addSeries(LineSeries, { color: "#1d4ed8", lineWidth: 2 });
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
