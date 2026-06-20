const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test.use({ ignoreHTTPSErrors: true });

test("whiteboard addon: admin whiteboard settings render and are wired to the collab backend", async ({ browser }) => {
  skipUnlessAddonEnabled("whiteboard");
  test.setTimeout(120_000);

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);

    await page.goto(
      new URL("settings/admin/whiteboard", shared.env.nextcloudBaseUrl).toString(),
      { waitUntil: "domcontentloaded", timeout: 60_000 }
    );
    await shared.dismissBlockingNextcloudModals(page, page);

    const adminSection = page
      .locator("#whiteboard_prefs, #whiteboard-settings, [data-cy='whiteboard-settings']")
      .or(page.getByText(/whiteboard server url|whiteboard backend|shared secret|jwt secret/i).first());
    await expect(
      adminSection.first(),
      "the Whiteboard admin settings section (settings/admin/whiteboard) must render, proving the whiteboard app is installed AND enabled (a disabled/broken app yields no section)"
    ).toBeVisible({ timeout: 60_000 });

    const backendUrlField = page.locator(
      "input#server-url, input[name='whiteboard-server-url'], input[type='url'][value*='whiteboard'], input[type='url']"
    );
    await expect(
      backendUrlField.first(),
      "the whiteboard collab-backend URL input must be present and prefilled — proving the addon's plugin_configuration (config:app:set whiteboard collabBackendUrl/jwt_secret_key) reached the running app"
    ).toBeVisible({ timeout: 30_000 });
    await expect(
      backendUrlField.first(),
      "the whiteboard collab-backend URL must be configured (NEXTCLOUD_WHITEBOARD_URL), not blank"
    ).not.toHaveValue("");
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
