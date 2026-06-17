"use client";

import { useEffect, useRef } from "react";
import { createChart } from "lightweight-charts";
import { EmptyState } from "@/components/empty-state";

export function PriceChart({ symbol }: { symbol: string }) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!containerRef.current || !symbol) {
      return;
    }
    const chart = createChart(containerRef.current, {
      height: 320,
      layout: { textColor: "#d6e0f0", background: { color: "#111827" } }
    });
    return () => chart.remove();
  }, [symbol]);

  if (!symbol) {
    return <EmptyState title="Select a symbol" description="Enter an A-share symbol to prepare the chart panel." />;
  }

  return (
    <section className="panel">
      <div className="panel__header">
        <h2>{symbol} Daily Chart</h2>
      </div>
      <div ref={containerRef} />
      <p className="muted">Market data unavailable until a daily bar endpoint is connected.</p>
    </section>
  );
}
