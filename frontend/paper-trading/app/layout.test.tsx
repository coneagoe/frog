import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SiteHeader } from "@/components/site-header";

describe("SiteHeader", () => {
  it("renders global navigation links to all paper trading pages", () => {
    render(<SiteHeader />);

    const links = [
      { name: "Accounts", href: "/accounts" },
      { name: "Trade", href: "/trade" },
      { name: "Orders", href: "/orders" },
      { name: "Trades", href: "/trades" },
      { name: "Analytics", href: "/analytics" }
    ];

    for (const { name, href } of links) {
      const link = screen.getByRole("link", { name });
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute("href", href);
    }
  });
});
