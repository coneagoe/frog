import Link from "next/link";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "Paper Trading",
  description: "A-share paper trading console"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="app-shell__header">
          <Link className="app-shell__brand" href="/accounts">
            Paper Trading
          </Link>
          <nav className="app-shell__nav" aria-label="Main navigation">
            <Link href="/accounts">Accounts</Link>
            <Link href="/trade">Trade</Link>
            <Link href="/analytics">Analytics</Link>
          </nav>
        </header>
        <main className="app-shell__main">{children}</main>
      </body>
    </html>
  );
}
