// Shared Zammad Playwright spec state: env vars consumed by more than one
// scenario, the OIDC sign-in helper that drives the SPA → Keycloak round-trip,
// the Zammad logout flow, and the beforeEach env-presence guard. Per-test env
// (admin credentials, biber credentials) is asserted inside the matching
// `test-*.js` file.

const { expect } = require("@playwright/test");

const { decodeDotenvQuotedValue, normalizeBaseUrl, performKeycloakLoginForm, runGuestFlow } = require("./personas");
const { isServiceEnabled, skipUnlessServiceEnabled } = require("./service-gating");

const oidcEnabled    = isServiceEnabled("oidc");
const oidcIssuerUrl  = normalizeBaseUrl(process.env.OIDC_ISSUER_URL || "");
const zammadBaseUrl  = normalizeBaseUrl(process.env.ZAMMAD_BASE_URL || "");
const adminUsername    = decodeDotenvQuotedValue(process.env.ADMIN_USERNAME);
const adminEmail       = decodeDotenvQuotedValue(process.env.ADMIN_EMAIL);
const adminPassword    = decodeDotenvQuotedValue(process.env.ADMIN_PASSWORD);
const adminApiUsername = decodeDotenvQuotedValue(process.env.ADMIN_API_USERNAME);
const adminApiPassword = decodeDotenvQuotedValue(process.env.ADMIN_API_PASSWORD);
const biberUsername  = decodeDotenvQuotedValue(process.env.BIBER_USERNAME);
const biberPassword  = decodeDotenvQuotedValue(process.env.BIBER_PASSWORD);
const canonicalDomain = decodeDotenvQuotedValue(process.env.CANONICAL_DOMAIN);

async function zammadLogout(page) {
  await page.goto(`${zammadBaseUrl}/#logout`, { waitUntil: "commit" }).catch(() => {});
  if (oidcIssuerUrl) {
    await page.goto(`${oidcIssuerUrl}/protocol/openid-connect/logout`, { waitUntil: "commit" }).catch(() => {});
  }
  await page.context().clearCookies();
}

async function signInAsApiBot(page) {
  // Server-side APIRequestContext (page.context().request) shares the
  // browser's cookie jar. Replaced an earlier in-page fetch approach that
  // produced a Keycloak-origin cross-origin error in OIDC variants; the
  // exact mechanism is not isolated, but this shape is what got
  // test-websocket-realtime to green.
  await page.context().clearCookies();

  const apiRequest = page.context().request;

  const seed = await apiRequest.get(`${zammadBaseUrl}/api/v1/getting_started`, {
    headers: { Accept: "application/json" },
    failOnStatusCode: true,
  });
  let csrfToken = seed.headers()["csrf-token"];
  if (!csrfToken) {
    const seedJson = await seed.json().catch(() => null);
    csrfToken = seedJson?.csrf_token;
  }
  if (!csrfToken) {
    throw new Error("could not lift csrf_token from getting_started");
  }

  const signin = await apiRequest.post(`${zammadBaseUrl}/api/v1/signin`, {
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      "X-CSRF-Token": csrfToken,
    },
    data: { username: adminApiUsername, password: adminApiPassword, fingerprint: "playwright" },
  });
  if (!signin.ok()) {
    throw new Error(`signin failed: ${signin.status()} ${await signin.text()}`);
  }

  await page.goto(`${zammadBaseUrl}/`, { waitUntil: "domcontentloaded" });
}

async function signInViaZammadOidc(page, username, password, personaLabel) {
  const expectedOidcAuthUrl = `${oidcIssuerUrl}/protocol/openid-connect/auth`;

  await page.goto(`${zammadBaseUrl}/`);

  const oidcSignIn = page
    .locator("a, button")
    .filter({ hasText: /openid|sign\s*in\s+with|continue\s+with|single\s+sign[-\s]*on|infinito/i })
    .first();

  if ((await oidcSignIn.count().catch(() => 0)) > 0) {
    await oidcSignIn.click();
  } else {
    await page.goto(`${zammadBaseUrl}/auth/openid_connect`).catch(() => {});
  }

  await expect
    .poll(() => page.url(), {
      timeout: 60_000,
      message: `${personaLabel}: expected redirect to Keycloak OIDC auth (${expectedOidcAuthUrl})`
    })
    .toContain(expectedOidcAuthUrl);

  await performKeycloakLoginForm(page, username, password);

  await expect
    .poll(() => page.url(), {
      timeout: 60_000,
      message: `${personaLabel}: expected redirect back to Zammad at ${zammadBaseUrl}`
    })
    .toContain(canonicalDomain);
}

async function beforeEach({ page }) {
  await page.setViewportSize({ width: 1440, height: 1100 });

  expect(zammadBaseUrl,   "ZAMMAD_BASE_URL must be set").toBeTruthy();
  expect(canonicalDomain, "CANONICAL_DOMAIN must be set").toBeTruthy();
  await page.context().clearCookies();
}

module.exports = {
  env: {
    oidcEnabled,
    oidcIssuerUrl,
    zammadBaseUrl,
    adminUsername,
    adminEmail,
    adminPassword,
    adminApiUsername,
    adminApiPassword,
    biberUsername,
    biberPassword,
    canonicalDomain,
  },
  signInViaZammadOidc,
  signInAsApiBot,
  zammadLogout,
  beforeEach,
  skipUnlessServiceEnabled,
  runGuestFlow,
};
