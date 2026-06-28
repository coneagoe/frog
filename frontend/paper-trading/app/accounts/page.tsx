import { Suspense } from "react";
import { AccountsPage } from "@/features/accounts/accounts-page";

export default function Page() {
  return (
    <Suspense fallback={<div className="panel">Loading accounts...</div>}>
      <AccountsPage />
    </Suspense>
  );
}
