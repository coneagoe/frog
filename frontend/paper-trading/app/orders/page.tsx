import { Suspense } from "react";
import { OrdersPage } from "@/features/history/orders-page";

export default function Page() {
  return (
    <Suspense fallback={<div className="panel">Loading orders...</div>}>
      <OrdersPage />
    </Suspense>
  );
}
