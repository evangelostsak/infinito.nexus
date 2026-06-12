// SeaweedFS object-store scenario for Baserow.
//
// Baserow is configured with S3 user-file storage (env.j2:
// AWS_STORAGE_BUCKET_NAME / AWS_S3_ENDPOINT_URL switch django-storages to the
// consumer bucket), so a file uploaded into a File-field cell is written to
// SeaweedFS as a new `user_files/...` object. The action signs the
// administrator in over OIDC (the same oauth2-proxy + Keycloak chain the
// suite's playwright.spec.js uses, reusing performKeycloakLoginForm), then
// builds the minimal surface needed for a real upload: a workspace database,
// a table, a File field, and a file dropped into that cell through the
// uploader dialog's hidden file input. The shared check proves the bucket
// grew via the Filer UI.

const { test, expect } = require("@playwright/test");
const { skipUnlessServiceEnabled } = require("./service-gating");
const {
  runSeaweedfsStorageCheck,
  performKeycloakLoginForm,
  normalizeBaseUrl,
  decodeDotenvQuotedValue,
} = require("./personas");

test.use({ ignoreHTTPSErrors: true });

test("seaweedfs: an uploaded Baserow file-field document is stored in the SeaweedFS bucket", async ({ page, browser }) => {
  skipUnlessServiceEnabled("seaweedfs");
  test.setTimeout(180_000);

  await runSeaweedfsStorageCheck(page, browser, {
    label: "a Baserow file-field upload",
    action: async (appPage) => {
      const baseUrl = normalizeBaseUrl(process.env.BASEROW_BASE_URL || "");
      const canonicalDomain = decodeDotenvQuotedValue(process.env.CANONICAL_DOMAIN || "");
      const adminUsername = decodeDotenvQuotedValue(process.env.ADMIN_USERNAME);
      const adminPassword = decodeDotenvQuotedValue(process.env.ADMIN_PASSWORD);
      const expectedBase = baseUrl.replace(/\/$/, "");

      expect(baseUrl, "BASEROW_BASE_URL must be set").toBeTruthy();
      expect(adminUsername, "ADMIN_USERNAME must be set").toBeTruthy();
      expect(adminPassword, "ADMIN_PASSWORD must be set").toBeTruthy();

      await appPage.context().clearCookies();
      await appPage.goto(`${expectedBase}/`, { waitUntil: "domcontentloaded" });

      if (!appPage.url().includes("openid-connect/auth")) {
        const loginLink = appPage
          .getByRole("link", { name: /log\s*in|sign\s*in|sso/i })
          .or(appPage.getByRole("button", { name: /log\s*in|sign\s*in|sso/i }))
          .first();
        if (await loginLink.isVisible({ timeout: 10_000 }).catch(() => false)) {
          await loginLink.click().catch(() => {});
        }
      }

      if (appPage.url().includes("openid-connect/auth")) {
        await performKeycloakLoginForm(appPage, adminUsername, adminPassword);
      }

      await expect
        .poll(() => appPage.url(), {
          timeout: 90_000,
          message: `expected redirect back to Baserow at ${canonicalDomain || expectedBase}`,
        })
        .toContain(canonicalDomain || expectedBase);

      await appPage.waitForLoadState("networkidle").catch(() => {});

      const skipOnboarding = appPage
        .getByRole("button", { name: /skip|later|maybe later|no thanks/i })
        .first();
      if (await skipOnboarding.isVisible({ timeout: 5_000 }).catch(() => false)) {
        await skipOnboarding.click().catch(() => {});
      }

      const createDatabase = appPage
        .getByText(/create.*(application|database)|new database|add database/i)
        .or(appPage.locator("a[href*='database'], .tree__add, .sidebar__new"))
        .first();
      if (await createDatabase.isVisible({ timeout: 30_000 }).catch(() => false)) {
        await createDatabase.click().catch(() => {});
        const databaseOption = appPage.getByText(/^\s*database\s*$/i).first();
        if (await databaseOption.isVisible({ timeout: 10_000 }).catch(() => false)) {
          await databaseOption.click().catch(() => {});
        }
        const createButton = appPage
          .getByRole("button", { name: /^\s*(create|add)\s*$/i })
          .first();
        if (await createButton.isVisible({ timeout: 10_000 }).catch(() => false)) {
          await createButton.click().catch(() => {});
        }
      }

      const gridView = appPage
        .locator(".grid-view, .grid-view__rows, [class*='gridView']")
        .first();
      await gridView.waitFor({ state: "visible", timeout: 60_000 }).catch(() => {});

      const addField = appPage
        .locator(".grid-view__add-column, [class*='addColumn'], button[title*='field' i]")
        .or(appPage.getByRole("button", { name: /add field|new field/i }))
        .first();
      if (await addField.isVisible({ timeout: 30_000 }).catch(() => false)) {
        await addField.click().catch(() => {});

        const typeDropdown = appPage
          .getByText(/select.*type|field type|choose a type/i)
          .or(appPage.locator(".dropdown__selected, [class*='fieldType']"))
          .first();
        if (await typeDropdown.isVisible({ timeout: 10_000 }).catch(() => false)) {
          await typeDropdown.click().catch(() => {});
        }
        const fileType = appPage.getByText(/^\s*file\s*$/i).first();
        if (await fileType.isVisible({ timeout: 10_000 }).catch(() => false)) {
          await fileType.click().catch(() => {});
        }
        const createField = appPage
          .getByRole("button", { name: /^\s*(create|add|save)\s*$/i })
          .first();
        if (await createField.isVisible({ timeout: 10_000 }).catch(() => false)) {
          await createField.click().catch(() => {});
        }
      }

      const fileCell = appPage
        .locator(".grid-field-file, [class*='fileField'], [class*='gridFieldFile']")
        .first();
      if (await fileCell.isVisible({ timeout: 30_000 }).catch(() => false)) {
        await fileCell.click().catch(() => {});
        const addFileButton = appPage
          .getByText(/add a file|add file/i)
          .or(appPage.locator(".grid-field-file__item-add, [class*='addFile']"))
          .first();
        if (await addFileButton.isVisible({ timeout: 10_000 }).catch(() => false)) {
          await addFileButton.click().catch(() => {});
        }
      }

      const markerBase = `infinito-storage-check-${Date.now()}`;
      const marker = `${markerBase}.txt`;
      const fileInput = appPage.locator('input[type="file"]').first();
      await fileInput.waitFor({ state: "attached", timeout: 60_000 });
      await fileInput.setInputFiles({
        name: marker,
        mimeType: "text/plain",
        buffer: Buffer.from(`infinito storage check ${marker}`),
      });

      const uploadConfirm = appPage
        .getByRole("button", { name: /^\s*(upload|add|done|save)\s*$/i })
        .first();
      if (await uploadConfirm.isVisible({ timeout: 10_000 }).catch(() => false)) {
        await uploadConfirm.click().catch(() => {});
      }

      // Baserow's file list renders the basename and the `.txt` extension as
      // separate nodes and truncates long names, so match the basename
      // (one contiguous node), falling back to any file container that holds it.
      await expect(
        appPage
          .getByText(markerBase, { exact: false })
          .or(
            appPage
              .locator(".grid-field-file__item, [class*='fileField'], [class*='gridFieldFile'], [class*='file']")
              .filter({ hasText: markerBase }),
          )
          .first(),
        `the uploaded file '${marker}' must be acknowledged in the Baserow UI`,
      ).toBeVisible({ timeout: 60_000 });
    },
  });
});
