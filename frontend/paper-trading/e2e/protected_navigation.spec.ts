import { expect, test } from "@playwright/test";

const account = {
  id: 1,
  name: "Continuation Account",
  initial_cash: "100000.0000",
  cash_available: "100000.0000",
  status: "active",
  base_currency: "CNY",
  fee_preset: "a_share_default",
  commission_rate: "0.000300",
  min_commission: "5.0000",
  stamp_duty_rate: "0.000500",
  transfer_fee_rate: "0.000010",
  share_count: "1.0000",
  net_asset_value: "100000.0000",
  cumulative_deposit: "100000.0000",
  cumulative_withdrawal: "0.0000"
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/paper/accounts", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: [account] });
      return;
    }
    await route.continue();
  });
});

test("browser registration, email verification, login, and protected navigation use session and CSRF cookies", async ({ page, request }, testInfo) => {
  const email = `e2e-auth-${testInfo.project.name}-${testInfo.parallelIndex}@example.test`;
  const password = "Validpassword1";

  await page.goto("/accounts");
  await expect(page).toHaveURL(/\/login\?return_to=%2Faccounts$/);

  await page.goto("/register");
  await page.getByLabel("Email address").fill(email);
  await page.locator("#auth-password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("status")).toHaveText(/Check your email/);

  const capturedMail = await request.get(`http://127.0.0.1:8100/__test__/mail/latest?email=${encodeURIComponent(email)}`);
  expect(capturedMail.ok()).toBeTruthy();
  const { verificationPath } = await capturedMail.json() as { verificationPath: string };

  await page.goto(verificationPath);
  await expect(page.getByRole("status")).toHaveText(/has been verified/);
  await page.getByRole("link", { name: "Back to login" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Email address").fill(email);
  await page.locator("#auth-password").fill(password);
  const [loginResponse] = await Promise.all([
    page.waitForResponse("**/api/auth/login"),
    page.getByRole("button", { name: "Log in" }).click()
  ]);
  expect(loginResponse.ok()).toBeTruthy();

  await expect.poll(async () => (await page.context().cookies()).map((cookie) => cookie.name)).toEqual(expect.arrayContaining(["paper_trading_session", "paper_trading_csrf"]));
  await page.goto("/accounts");
  await expect(page).toHaveURL(/\/accounts$/);
  await expect(page.getByRole("heading", { name: "Continuation Account" })).toBeVisible();
});

test("protected navigation resumes after login with session and CSRF cookies", async ({ page }) => {
  await page.route("**/api/auth/login", async (route) => {
    await route.fulfill({
      json: { id: 1, email: "trader@example.com", email_verified_at: null },
      headers: {
        "set-cookie": "paper_trading_session=session-token; Path=/; HttpOnly; SameSite=Lax\npaper_trading_csrf=csrf-token; Path=/; SameSite=Lax"
      }
    });
  });

  await page.goto("/monitor");
  await expect(page).toHaveURL(/\/login\?return_to=%2Fmonitor$/);
  await page.getByLabel("Email address").fill("trader@example.com");
  await page.locator("#auth-password").fill("Validpassword1");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/monitor$/);
  await expect(page.getByRole("heading", { name: "Operational health" })).toBeVisible();
  await expect.poll(async () => (await page.context().cookies()).map((cookie) => cookie.name)).toEqual(expect.arrayContaining(["paper_trading_session", "paper_trading_csrf"]));
});

test("login falls back to accounts for an external return path", async ({ page }) => {
  await page.route("**/api/auth/login", async (route) => {
    await route.fulfill({
      json: { id: 1, email: "trader@example.com", email_verified_at: null },
      headers: {
        "set-cookie": "paper_trading_session=session-token; Path=/; HttpOnly; SameSite=Lax\npaper_trading_csrf=csrf-token; Path=/; SameSite=Lax"
      }
    });
  });

  await page.goto("/login?return_to=%2F%2Fevil.example");
  await page.getByLabel("Email address").fill("trader@example.com");
  await page.locator("#auth-password").fill("Validpassword1");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/accounts$/);
  await expect(page.getByRole("heading", { name: "Continuation Account" })).toBeVisible();
});
