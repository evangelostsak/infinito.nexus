const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test.use({ ignoreHTTPSErrors: true });

test("fileslibreofficeedit addon: the LibreOffice editor app renders its own admin settings surface", async ({ browser }) => {
  skipUnlessAddonEnabled("fileslibreofficeedit");
  test.setTimeout(120_000);

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);

    const settingsUrl = new URL("settings/admin/fileslibreofficeedit", shared.env.nextcloudBaseUrl).toString();
    const response = await page.goto(settingsUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });
    expect(
      response === null || response.status() !== 404,
      "the fileslibreofficeedit admin settings route must not 404: a 404 means the app is disabled/absent at runtime",
    ).toBeTruthy();
    await shared.dismissBlockingNextcloudModals(page, page);

    const settingsPanel = page
      .locator("#fileslibreofficeedit, [data-section-id='fileslibreofficeedit'], #app-content #fileslibreofficeedit")
      .or(page.getByRole("heading", { name: /libreoffice/i }))
      .first();
    await expect(
      settingsPanel,
      "the fileslibreofficeedit app must render its own LibreOffice editor admin settings section, proving the app is enabled (not just listed)",
    ).toBeVisible({ timeout: 60_000 });

    const serverUrlField = page
      .locator("#fileslibreofficeedit input[type='url'], #fileslibreofficeedit input[type='text'], input#wopi_url, input[name*='url' i]")
      .first();
    await expect(
      serverUrlField,
      "the fileslibreofficeedit admin section must expose its document-editor server URL field, proving its own settings form (not a generic shell) is rendered",
    ).toBeVisible({ timeout: 60_000 });
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
