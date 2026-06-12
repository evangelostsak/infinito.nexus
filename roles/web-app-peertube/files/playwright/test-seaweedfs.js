// SeaweedFS object-store scenario for PeerTube.
//
// PeerTube is configured with S3 object storage for web videos
// (PEERTUBE_OBJECT_STORAGE_ENABLED=true,
// PEERTUBE_OBJECT_STORAGE_WEB_VIDEOS_BUCKET_NAME -> the consumer bucket,
// PEERTUBE_OBJECT_STORAGE_WEB_VIDEOS_PREFIX=web-videos/). Avatars/thumbnails
// stay on the local volume in this config, so the only user action that lands
// in S3 is a video upload: PeerTube stores the web video locally and a
// background job moves it into the bucket under web-videos/. The action signs
// the administrator in over OIDC (mirroring playwright.spec.js), uploads a
// minimal valid MP4 through the upload UI and waits for it to be published;
// the shared check then proves the bucket grew via the Filer UI.

const { test, expect } = require("@playwright/test");
const { skipUnlessServiceEnabled } = require("./service-gating");
const {
  runSeaweedfsStorageCheck,
  performKeycloakLoginForm,
  decodeDotenvQuotedValue,
  normalizeBaseUrl,
} = require("./personas");

test.use({ ignoreHTTPSErrors: true });

const peertubeBaseUrl = normalizeBaseUrl(process.env.PEERTUBE_BASE_URL || "");
const oidcIssuerUrl = normalizeBaseUrl(process.env.OIDC_ISSUER_URL || "");
const oidcButtonText = decodeDotenvQuotedValue(process.env.OIDC_BUTTON_TEXT || "");
const adminUsername = decodeDotenvQuotedValue(process.env.ADMIN_USERNAME || "");
const adminPassword = decodeDotenvQuotedValue(process.env.ADMIN_PASSWORD || "");

function minimalMp4Buffer() {
  const base64 =
    "AAAAGGZ0eXBpc29tAAAAAGlzb21pc28yAAAACGZyZWUAAAAtbWRhdAAAAAAAAAAA" +
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
  return Buffer.from(base64, "base64");
}

async function loginAdminViaOidc(page) {
  await page.goto(`${peertubeBaseUrl}/login`, { waitUntil: "domcontentloaded" });

  const oidcButtonPatterns = [
    oidcButtonText ? new RegExp(oidcButtonText.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i") : null,
    /open\s*id\s*connect/i,
    /single\s+sign[-\s]*on/i,
    /continue\s+with\s+oidc/i,
    /sign\s*in\s+with\s+oidc/i,
  ].filter(Boolean);

  for (const pattern of oidcButtonPatterns) {
    const candidate = page.locator("a, button").filter({ hasText: pattern }).first();
    if ((await candidate.count().catch(() => 0)) > 0) {
      await candidate.click().catch(() => {});
      break;
    }
  }

  await expect
    .poll(() => page.url(), {
      timeout: 60_000,
      message: `expected redirect to Keycloak OIDC auth (${oidcIssuerUrl}/protocol/openid-connect/auth)`,
    })
    .toContain(`${oidcIssuerUrl}/protocol/openid-connect/auth`);

  await performKeycloakLoginForm(page, adminUsername, adminPassword);

  await expect
    .poll(() => page.url(), {
      timeout: 60_000,
      message: `expected redirect back to PeerTube at ${peertubeBaseUrl}`,
    })
    .toContain(peertubeBaseUrl);

  const authenticatedMarker = page
    .locator("my-avatar-menu, my-user-notifications, my-header my-avatar, a[href='/my-account'], button.dropdown-toggle my-avatar")
    .first();
  await expect(authenticatedMarker, "expected an authenticated PeerTube UI marker after OIDC login").toBeVisible({
    timeout: 60_000,
  });
}

async function uploadWebVideo(page) {
  await page.goto(`${peertubeBaseUrl}/videos/upload`, { waitUntil: "domcontentloaded" });

  const marker = `infinito-storage-check-${Date.now()}`;

  const fileInput = page.locator("input[type='file']").first();
  await fileInput.waitFor({ state: "attached", timeout: 60_000 });
  await fileInput.setInputFiles({
    name: `${marker}.mp4`,
    mimeType: "video/mp4",
    buffer: minimalMp4Buffer(),
  });

  const nameField = page
    .getByLabel(/name/i)
    .or(page.locator("input#name, input[formcontrolname='name'], input[name='name']"))
    .first();
  await nameField.waitFor({ state: "visible", timeout: 60_000 });
  await nameField.fill(marker);

  const publishButton = page
    .getByRole("button", { name: /^\s*publish\b/i })
    .or(page.locator("button.orange-button[type='submit'], my-button[type='submit'] button, button[type='submit']"))
    .first();
  await publishButton.waitFor({ state: "visible", timeout: 60_000 });

  await expect
    .poll(async () => (await publishButton.isEnabled().catch(() => false)) === true, {
      timeout: 120_000,
      message: "expected the PeerTube publish button to become enabled after the upload finishes",
    })
    .toBe(true);

  await publishButton.click();

  const publishedMarker = page
    .locator("my-video-watch, .video-info-name, h1.video-info-name")
    .or(page.getByRole("heading", { name: marker }))
    .or(page.getByText(marker, { exact: false }))
    .first();
  await expect(
    publishedMarker,
    `the uploaded video '${marker}' must be accepted by PeerTube before the S3 move job runs`,
  ).toBeVisible({ timeout: 120_000 });
}

test("seaweedfs: an uploaded PeerTube video is stored in the SeaweedFS bucket", async ({ page, browser }) => {
  skipUnlessServiceEnabled("seaweedfs");
  test.setTimeout(180_000);

  await runSeaweedfsStorageCheck(page, browser, {
    label: "a PeerTube video upload",
    action: async (appPage) => {
      await loginAdminViaOidc(appPage);
      await uploadWebVideo(appPage);
    },
  });
});
