const { expect } = require("@playwright/test");

const {
  decodeDotenvQuotedValue,
  installCspViolationObserver,
  normalizeBaseUrl,
  performKeycloakLoginForm,
} = require("./personas");

const env = {
  oidcIssuerUrl: normalizeBaseUrl(process.env.OIDC_ISSUER_URL || ""),
  openwebuiBaseUrl: normalizeBaseUrl(process.env.OPENWEBUI_BASE_URL || ""),
  adminUsername: decodeDotenvQuotedValue(process.env.ADMIN_USERNAME),
  adminPassword: decodeDotenvQuotedValue(process.env.ADMIN_PASSWORD),
  biberUsername: decodeDotenvQuotedValue(process.env.BIBER_USERNAME),
  biberPassword: decodeDotenvQuotedValue(process.env.BIBER_PASSWORD),
  canonicalDomain: decodeDotenvQuotedValue(process.env.CANONICAL_DOMAIN),
};

function attachDiagnostics(page) {
  const consoleErrors = [];
  const pageErrors = [];
  const cspRelated = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
    if (/content security policy|csp/i.test(message.text())) {
      cspRelated.push({ source: "console", text: message.text() });
    }
  });
  page.on("pageerror", (error) => {
    const text = String(error);
    pageErrors.push(text);
    if (/content security policy|csp/i.test(text)) {
      cspRelated.push({ source: "pageerror", text });
    }
  });
  return { consoleErrors, pageErrors, cspRelated };
}

async function openwebuiLogout(page, openwebuiBaseUrl) {
  await page
    .goto(`${openwebuiBaseUrl}/logout`, { waitUntil: "commit" })
    .catch(() => {});
}

async function signInViaDashboardOidc(page, username, password, personaLabel) {
  const expectedOidcAuthUrl = `${env.oidcIssuerUrl}/protocol/openid-connect/auth`;

  await page.goto(`${env.openwebuiBaseUrl}/`);

  const oidcSignIn = page
    .locator("a, button")
    .filter({ hasText: /sign\s*in\s+with\s+oidc|sign\s*in\s+with\s+sso|continue\s+with\s+oidc|continue\s+with\s+sso|single\s+sign[-\s]*on/i })
    .first();

  if ((await oidcSignIn.count().catch(() => 0)) > 0) {
    await oidcSignIn.click();
  } else {
    await page.goto(`${env.openwebuiBaseUrl}/oauth/oidc/login`).catch(() => {});
  }

  await expect
    .poll(() => page.url(), {
      timeout: 60_000,
      message: `${personaLabel}: expected redirect to Keycloak OIDC auth (${expectedOidcAuthUrl})`,
    })
    .toContain(expectedOidcAuthUrl);

  await performKeycloakLoginForm(page, username, password);

  await expect
    .poll(() => page.url(), {
      timeout: 60_000,
      message: `${personaLabel}: expected redirect back to openwebui at ${env.openwebuiBaseUrl}`,
    })
    .toContain(env.openwebuiBaseUrl);
}

async function expectSignInRequiredAfterLogout(page) {
  await openwebuiLogout(page, env.openwebuiBaseUrl);
  await page.goto(`${env.openwebuiBaseUrl}/`);
  await expect
    .poll(
      async () =>
        (await page
          .locator("a, button")
          .filter({ hasText: /sign\s*in|log\s*in|anmelden|continue\s+with/i })
          .first()
          .count()
          .catch(() => 0)) > 0,
      {
        timeout: 60_000,
        message: "Expected openwebui to require a new sign-in after logout",
      }
    )
    .toBe(true);
}

async function beforeEach({ page }) {
  await page.setViewportSize({ width: 1440, height: 1100 });
  expect(env.oidcIssuerUrl, "OIDC_ISSUER_URL must be set").toBeTruthy();
  expect(env.openwebuiBaseUrl, "OPENWEBUI_BASE_URL must be set").toBeTruthy();
  expect(env.adminUsername, "ADMIN_USERNAME must be set").toBeTruthy();
  expect(env.adminPassword, "ADMIN_PASSWORD must be set").toBeTruthy();
  expect(env.biberUsername, "BIBER_USERNAME must be set").toBeTruthy();
  expect(env.biberPassword, "BIBER_PASSWORD must be set").toBeTruthy();
  expect(env.canonicalDomain, "CANONICAL_DOMAIN must be set").toBeTruthy();
  await page.context().clearCookies();
  await installCspViolationObserver(page);
}

module.exports = {
  env,
  attachDiagnostics,
  openwebuiLogout,
  signInViaDashboardOidc,
  expectSignInRequiredAfterLogout,
  beforeEach,
};
