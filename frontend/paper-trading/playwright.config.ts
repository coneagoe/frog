import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:3100",
    browserName: "chromium",
    colorScheme: "light",
    locale: "en-US",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    video: "off"
  },
  expect: {
    toHaveScreenshot: {
      animations: "disabled",
      caret: "hide",
      scale: "css"
    }
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 900 } }
    },
    {
      name: "mobile",
      use: { ...devices["Pixel 5"], viewport: { width: 390, height: 844 } }
    }
  ],
  webServer: [
    {
      command: "node e2e/auth_test_server.mjs",
      reuseExistingServer: false,
      url: "http://127.0.0.1:8100"
    },
    {
      command: "npm run dev -- --hostname 127.0.0.1 --port 3100",
      env: { PAPER_TRADING_API_BASE_URL: "http://127.0.0.1:8100" },
      reuseExistingServer: false,
      url: "http://127.0.0.1:3100"
    }
  ]
});
