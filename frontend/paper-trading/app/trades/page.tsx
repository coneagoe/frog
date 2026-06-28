import { Suspense } from "react";
import { TradesPage } from "@/features/history/trades-page";

export default function Page() {
  return (
    <Suspense fallback={<div className="panel">Loading trades...</div>}>
      <TradesPage />
    </Suspense>
  );
}
