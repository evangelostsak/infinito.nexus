const { test, expect } = require("@playwright/test");
const { skipUnlessServiceEnabled } = require("./service-gating");
const { runSeaweedfsStorageCheck } = require("./personas");
const shared = require("./_shared");

const PNG_1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
);

test.use({ ignoreHTTPSErrors: true });

test("seaweedfs: an uploaded Taiga avatar is stored in the SeaweedFS bucket", async ({ page, browser }) => {
  skipUnlessServiceEnabled("seaweedfs");
  test.setTimeout(180_000);

  await runSeaweedfsStorageCheck(page, browser, {
    label: "a Taiga user avatar upload",
    action: async (appPage) => {
      const taigaUrls = await shared.loginToTaiga(appPage);

      await appPage.goto(taigaUrls.userSettingsUrl, { waitUntil: "domcontentloaded" });

      const fileInput = appPage.locator('input[type="file"]').first();
      await expect(
        fileInput,
        "the Taiga user-profile page must expose a file input to change the avatar photo",
      ).toBeAttached({ timeout: 60_000 });

      const marker = `infinito-storage-check-${Date.now()}.png`;
      await fileInput.setInputFiles({
        name: marker,
        mimeType: "image/png",
        buffer: PNG_1x1,
      });

      const saveAction = appPage
        .getByRole("button", { name: /save|upload|change/i })
        .or(appPage.locator('button[type="submit"], a.button-save, .save'))
        .first();
      if (await saveAction.isVisible({ timeout: 10_000 }).catch(() => false)) {
        await saveAction.click().catch(() => {});
      }
    },
  });
});
