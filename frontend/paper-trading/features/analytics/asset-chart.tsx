"use client";

import { useEffect, useMemo, useRef } from "react";
import { createChart, LineSeries, type UTCTimestamp } from "lightweight-charts";
import { EmptyState } from "@/components/empty-state";
import type { AnalyticsEvent, Snapshot } from "@/lib/types";

export function AssetChart({ events }: { events: Array<AnalyticsEvent | Snapshot> }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartData = useMemo(
    () => {
      let previousTime: number | null = null;
      return events.flatMap((event) => {
        if ("event_type" in event && event.event_type !== "snapshot") {
          return [];
        }
        const snapshot = event as Snapshot | Extract<AnalyticsEvent, { event_type: "snapshot" }>;
        const navValue = "event_type" in snapshot ? snapshot.nav : snapshot.net_asset_value;
        if (!("event_type" in snapshot) && !("net_asset_value" in snapshot)) return [];
        const nav = Number(navValue);
        const timestamp = Math.floor(new Date(snapshot.event_at).getTime() / 1000);
        if (
          snapshot.quality_status !== "valid"
          || navValue === null
          || !Number.isFinite(nav)
          || nav <= 0
          || !Number.isFinite(timestamp)
        ) {
          return [];
        }
        const time = Math.max(timestamp, (previousTime ?? timestamp - 1) + 1);
        previousTime = time;
        return [{ time: time as UTCTimestamp, value: nav }];
      });
    },
    [events]
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
