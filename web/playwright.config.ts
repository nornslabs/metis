import { defineConfig, devices } from "@playwright/test";

// Runs against an already-running stack (`AGENT_STUB_SPECIALISTS=true docker compose up`:
// the e2e runs use stub specialists, as the stack has no LLM key); set E2E_BASE_URL to
// point elsewhere.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  globalSetup: "./e2e/support/global-setup.ts",
  globalTeardown: "./e2e/support/global-teardown.ts",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
