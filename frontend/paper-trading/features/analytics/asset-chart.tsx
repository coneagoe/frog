"use client";

import { useEffect, useMemo, useRef } from "react";
import { createChart, LineSeries, type UTCTimestamp } from "lightweight-charts";
import { EmptyState } from "@/components/empty-state";
import type { AnalyticsEvent } from "@/lib/types";

function toTradeDateUtcTimestamp(tradeDate: string): number | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(tradeDate);
  if (!match) return null;
  const [, year, month, day] = match.map(Number);
  const milliseconds = Date.UTC(year, month - 1, day, 23, 59, 59);
  const check = new Date(milliseconds);
  return check.getUTCFullYear() === year && check.getUTCMonth() === month - 1 && check.getUTCDate() === day
    ? Math.floor(milliseconds / 1000)
    : null;
}

export function AssetChart({ events }: { events: AnalyticsEvent[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartData = useMemo(
    () => {
      let previousTime: number | null = null;
      return events.flatMap((event) => {
        if (event.event_type !== "snapshot" || !["initial", "trading"].includes(event.point_type)) {
          return [];
        }
        const nav = Number(event.nav);
        const timestamp = toTradeDateUtcTimestamp(event.trade_date);
        if (
          event.quality !== "valid"
          || event.nav === null
          || !Number.isFinite(nav)
          || nav <= 0
          || timestamp === null
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
    return <EmptyState title="No valid NAV points" description="Run matching to generate account valuation snapshots." />;
  }

  return (
    <div className="panel chart-surface">
      <div ref={containerRef} />
    </div>
  );
}
