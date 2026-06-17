import { Suspense } from "react";
import { AnalyticsPage } from "@/features/analytics/analytics-page";

export default function Page() {
  return (
    <Suspense fallback={<div className="panel">Loading paper trading data...</div>}>
      <AnalyticsPage />
    </Suspense>
  );
}
