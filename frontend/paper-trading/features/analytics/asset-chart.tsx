"use client";

import { useEffect, useMemo, useRef } from "react";
import { createChart, LineSeries, type UTCTimestamp } from "lightweight-charts";
import { EmptyState } from "@/components/empty-state";
import type { Snapshot } from "@/lib/types";

export function AssetChart({ snapshots }: { snapshots: Snapshot[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartData = useMemo(
    () => snapshots.flatMap((snapshot) => {
      const nav = Number(snapshot.net_asset_value);
      if (snapshot.quality_status !== "valid" || snapshot.net_asset_value === null || !Number.isFinite(nav) || nav <= 0) {
        return [];
      }
      return [{ time: Math.floor(new Date(snapshot.event_at).getTime() / 1000) as UTCTimestamp, value: nav }];
    }),
    [snapshots]
  );

  useEffect(() => {
    if (!containerRef.current || chartData.length === 0) {
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
    series.setData(chartData);
    return () => chart.remove();
  }, [chartData]);

  if (chartData.length === 0) {
    return <EmptyState title="No snapshots yet" description="Run matching to generate account valuation snapshots." />;
  }

  return (
    <div className="panel chart-surface">
      <div ref={containerRef} />
    </div>
  );
}
