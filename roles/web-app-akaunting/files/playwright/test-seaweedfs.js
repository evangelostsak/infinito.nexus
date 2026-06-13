const { test, expect } = require("@playwright/test");
const { skipUnlessServiceEnabled } = require("./service-gating");
const {
  runSeaweedfsStorageCheck,
  performKeycloakLoginForm,
  decodeDotenvQuotedValue,
  normalizeBaseUrl,
} = require("./personas");

const PNG_1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
);

const baseUrl = normalizeBaseUrl(process.env.AKAUNTING_BASE_URL || "");
const canonicalDomain = decodeDotenvQuotedValue(process.env.CANONICAL_DOMAIN || "");
const adminUsername = decodeDotenvQuotedValue(process.env.ADMIN_USERNAME);
const adminPassword = decodeDotenvQuotedValue(process.env.ADMIN_PASSWORD);

test.use({ ignoreHTTPSErrors: true });

test("seaweedfs: an uploaded Akaunting company logo is stored in the SeaweedFS bucket", async ({ page, browser }) => {
  skipUnlessServiceEnabled("seaweedfs");
  test.setTimeout(180_000);

  expect(baseUrl, "AKAUNTING_BASE_URL must be set").toBeTruthy();
  expect(canonicalDomain, "CANONICAL_DOMAIN must be set").toBeTruthy();
  expect(adminUsername).toBeTruthy();
  expect(adminPassword).toBeTruthy();

  const expectedBase = baseUrl.replace(/\/$/, "");

  await runSeaweedfsStorageCheck(page, browser, {
    label: "an Akaunting company logo upload",
    action: async (appPage) => {
      await appPage.context().clearCookies();
      await appPage.goto(`${expectedBase}/`, { waitUntil: "domcontentloaded" });
      if (appPage.url().includes("openid-connect/auth")) {
        await performKeycloakLoginForm(appPage, adminUsername, adminPassword);
        await expect.poll(() => appPage.url(), { timeout: 90_000 }).toContain(expectedBase);
      }

      await appPage.goto(`${expectedBase}/1/settings/company`, { waitUntil: "domcontentloaded" });
      await expect
        .poll(() => appPage.url(), { timeout: 90_000, message: "expected the Akaunting company settings page" })
        .toContain("settings/company");

      const marker = `infinito-storage-check-${Date.now()}.png`;
      const fileInput = appPage.locator('input[type="file"]').first();
      await fileInput.waitFor({ state: "attached", timeout: 60_000 });
      await fileInput.setInputFiles({ name: marker, mimeType: "image/png", buffer: PNG_1x1 });

      const saveAction = appPage
        .getByRole("button", { name: /^(save|update)$/i })
        .or(appPage.locator("button[type='submit'], #index-more-actions button.button-submit"))
        .first();
      await expect(
        saveAction,
        "the Akaunting company settings form must expose a Save action to persist the attached logo",
      ).toBeVisible({ timeout: 60_000 });
      await saveAction.click();

      await appPage.waitForLoadState("networkidle", { timeout: 90_000 }).catch(() => {});
    },
  });
});
