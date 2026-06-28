import type { ReactNode } from "react";
import { SiteHeader } from "@/components/site-header";
import "./globals.css";

export const metadata = {
  title: "Paper Trading",
  description: "A-share paper trading console"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SiteHeader />
        <main className="app-shell__main">{children}</main>
      </body>
    </html>
  );
}
