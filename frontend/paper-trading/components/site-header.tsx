import Link from "next/link";

export function SiteHeader() {
  return (
    <header className="app-shell__header">
      <Link className="app-shell__brand" href="/accounts">
        Paper Trading
      </Link>
      <nav className="app-shell__nav" aria-label="Main navigation">
        <Link href="/accounts">Accounts</Link>
        <Link href="/trade">Trade</Link>
        <Link href="/orders">Orders</Link>
        <Link href="/trades">Trades</Link>
        <Link href="/analytics">Analytics</Link>
      </nav>
    </header>
  );
}
