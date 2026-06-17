import { Suspense } from "react";
import { TradePage } from "@/features/trading/trade-page";

export default function Page() {
  return (
    <Suspense fallback={<div className="panel">Loading paper trading data...</div>}>
      <TradePage />
    </Suspense>
  );
}
