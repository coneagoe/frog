import { test, expect } from "@playwright/test";

const account = {
  id: 1,
  name: "Demo Ledger",
  initial_cash: "100000.0000",
  cash_available: "74215.5000",
  status: "active",
  base_currency: "CNY",
  fee_preset: "a_share_default",
  commission_rate: "0.000300",
  min_commission: "5.0000",
  stamp_duty_rate: "0.000500",
  transfer_fee_rate: "0.000010",
  share_count: "1.0000",
  net_asset_value: "101234.5600",
  cumulative_deposit: "100000.0000",
  cumulative_withdrawal: "0.0000"
};

const positions = [
  {
    symbol: "600000",
    stock_name: "Pudong Development Bank",
    total_quantity: 1200,
    frozen_quantity: 0,
    cost_amount: "10800.0000",
    realized_pnl: "0.0000",
    mark_price: "9.4200",
    price_source: "db_close",
    unrealized_pnl: "504.0000"
  },
  {
    symbol: "000001",
    stock_name: "Ping An Bank",
    total_quantity: 800,
    frozen_quantity: 100,
    cost_amount: "9600.0000",
    realized_pnl: "120.0000",
    mark_price: "12.1800",
    price_source: "db_close",
    unrealized_pnl: "144.0000"
  }
];

test.beforeEach(async ({ page }) => {
  await page.route("**/api/paper/accounts", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: [account] });
      return;
    }
    await route.continue();
  });
  await page.route("**/api/paper/accounts/1/positions", async (route) => {
    await route.fulfill({ json: positions });
  });
});

test("renders the account ledger desk", async ({ page }) => {
  await page.goto("/accounts");
  await expect(page.getByRole("heading", { name: "Demo Ledger" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "600000" })).toBeVisible();
  await expect(page).toHaveScreenshot("ledger-desk.png", { fullPage: true });
});
