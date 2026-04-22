const { test, expect } = require("@playwright/test");

test.use({
  ignoreHTTPSErrors: true
});

function decodeDotenvQuotedValue(value) {
  if (typeof value !== "string" || value.length < 2) {
    return value;
  }

  if (!(value.startsWith('"') && value.endsWith('"'))) {
    return value;
  }

  const encoded = value.slice(1, -1);

  try {
    return JSON.parse(`"${encoded}"`).replace(/\$\$/g, "$");
  } catch {
    return encoded.replace(/\$\$/g, "$");
  }
}

// `docker --env-file` preserves the quotes emitted by `dotenv_quote`,
// so normalize these values before building URLs or typing credentials.
const oidcIssuerUrl  = decodeDotenvQuotedValue(process.env.OIDC_ISSUER_URL);
const penpotBaseUrl  = decodeDotenvQuotedValue(process.env.PENPOT_BASE_URL);
const adminUsername  = decodeDotenvQuotedValue(process.env.ADMIN_USERNAME);
const adminPassword  = decodeDotenvQuotedValue(process.env.ADMIN_PASSWORD);
const biberUsername  = decodeDotenvQuotedValue(process.env.BIBER_USERNAME);
const biberPassword  = decodeDotenvQuotedValue(process.env.BIBER_PASSWORD);

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

async function findFirstVisible(locators) {
  for (const locator of locators) {
    const candidate = locator.first();

    if (await candidate.isVisible().catch(() => false)) {
      return candidate;
    }
  }

  return null;
}

// Perform OIDC login via Keycloak.
// Accepts a Page or FrameLocator (when Keycloak loads inside the dashboard iframe).
async function performOidcLogin(locator, username, password) {
  const usernameField = locator.getByRole("textbox", { name: /username|email/i });
  const passwordField = locator.getByRole("textbox", { name: "Password" });
  const signInButton  = locator.getByRole("button", { name: /sign in/i });

  await usernameField.waitFor({ state: "visible", timeout: 60_000 });
  await usernameField.fill(username);
  await usernameField.press("Tab");
  await passwordField.fill(password);
  await signInButton.click();
}

// Click the OIDC login button on Penpot's login page.
// Penpot renders the OIDC button as a link pointing to /api/rpc/command/login-with-oidc.
function getPenpotOidcEntryLocators(locator) {
  const oidcLabelPattern = /oidc|single sign-on|sso|keycloak/i;

  return [
    locator.locator("a.main_ui_auth_login__btn-oidc-auth, button.main_ui_auth_login__btn-oidc-auth"),
    locator.getByRole("link", { name: oidcLabelPattern }),
    locator.getByRole("button", { name: oidcLabelPattern }),
    locator.locator("a[href*='login-with-oidc'], a[href*='/api/auth/oidc'], a[href*='oidc']"),
    locator.locator("button[data-testid*='oidc'], [data-testid*='oidc']"),
    locator.locator("[class*='oidc'], [class*='sso']")
  ];
}

async function triggerPenpotOidcLogin(page, iframeLocator, penpotFrame, expectedOidcAuthUrl) {
  const directButton = penpotFrame.locator("a.main_ui_auth_login__btn-oidc-auth, button.main_ui_auth_login__btn-oidc-auth").first();

  if (await directButton.count()) {
    await directButton.click({ force: true });
  } else {
    const entry = await findFirstVisible(getPenpotOidcEntryLocators(penpotFrame));

    if (entry) {
      await entry.click({ force: true });
    }
  }

  await expect
    .poll(
      async () => {
        const iframeHandle = await iframeLocator.first().elementHandle();
        const frame = iframeHandle ? await iframeHandle.contentFrame() : null;
        return frame ? frame.url() : "";
      },
      {
        timeout: 15_000,
        message: "Expected iframe to navigate to Keycloak after clicking OIDC login"
      }
    )
    .toContain(expectedOidcAuthUrl);
}

async function waitForPenpotOidcEntry(page, iframeLocator, penpotFrame, expectedPenpotBaseUrl, expectedOidcAuthUrl, timeout, errorMessage) {
  const deadline = Date.now() + timeout;

  while (Date.now() < deadline) {
    const iframeHandle = await iframeLocator.first().elementHandle();
    const frame = iframeHandle ? await iframeHandle.contentFrame() : null;
    const frameUrl = frame ? frame.url() : "";

    if (frameUrl.includes(expectedOidcAuthUrl) || frameUrl.includes("/protocol/openid-connect/auth")) {
      return { kind: "keycloak" };
    }

    if (frameUrl.includes(expectedPenpotBaseUrl)) {
      const oidcEntry = await findFirstVisible(getPenpotOidcEntryLocators(penpotFrame));

      if (oidcEntry) {
        return { kind: "penpot-oidc-entry", locator: oidcEntry };
      }

      const loginEntry = await findFirstVisible([
        penpotFrame.getByRole("link", { name: /log in|login|sign in/i }),
        penpotFrame.getByRole("button", { name: /log in|login|sign in/i })
      ]);

      if (loginEntry) {
        await loginEntry.click();
        await page.waitForTimeout(500);
      }
    }

    await page.waitForTimeout(500);
  }

  throw new Error(errorMessage);
}

// Check if user is authenticated in Penpot.
// After login, Penpot shows either dashboard/projects or first-login onboarding.
async function isPenpotAuthenticated(locator) {
  try {
    // Returning users land on dashboard/workspace.
    const nav          = locator.locator("nav, [class*='main-nav'], [class*='navbar']");
    const projectList  = locator.locator("[class*='project'], [class*='dashboard'], [class*='workspace']");
    const userMenu     = locator.locator("[class*='user-menu'], [class*='profile-menu'], [aria-label*='user']");
    // First-time users land on profile completion (still authenticated).
    const onboardingTitle = locator.getByRole("heading", { name: /your name/i });
    const createAccountButton = locator.getByRole("button", { name: /create an account/i });
    const fullNameField = locator.getByRole("textbox", { name: /full name/i });

    return (
      await nav.first().isVisible().catch(() => false) ||
      await projectList.first().isVisible().catch(() => false) ||
      await userMenu.first().isVisible().catch(() => false) ||
      await onboardingTitle.first().isVisible().catch(() => false) ||
      await createAccountButton.first().isVisible().catch(() => false) ||
      await fullNameField.first().isVisible().catch(() => false)
    );
  } catch {
    return false;
  }
}

// Wait for the iframe URL to contain a specific string.
async function waitForFrameUrl(iframeLocator, matcher, timeout, errorMessage) {
  await expect
    .poll(
      async () => {
        const iframeHandle = await iframeLocator.elementHandle();
        const frame = iframeHandle ? await iframeHandle.contentFrame() : null;
        return frame ? frame.url() : "";
      },
      { timeout, message: errorMessage }
    )
    .toContain(matcher);
}

async function ensurePenpotLoggedOut(page, expectedPenpotBaseUrl) {
  await page.goto(`/?iframe=${encodeURIComponent(expectedPenpotBaseUrl + "/logout")}`);
  await page.waitForTimeout(1_500);
}

test.beforeEach(() => {
  expect(oidcIssuerUrl,  "OIDC_ISSUER_URL must be set in the Playwright env file").toBeTruthy();
  expect(penpotBaseUrl,  "PENPOT_BASE_URL must be set in the Playwright env file").toBeTruthy();
  expect(adminUsername,  "ADMIN_USERNAME must be set in the Playwright env file").toBeTruthy();
  expect(adminPassword,  "ADMIN_PASSWORD must be set in the Playwright env file").toBeTruthy();
  expect(biberUsername,  "BIBER_USERNAME must be set in the Playwright env file").toBeTruthy();
  expect(biberPassword,  "BIBER_PASSWORD must be set in the Playwright env file").toBeTruthy();
});

// Scenario I: dashboard → Penpot iframe → SSO login as admin → verify authenticated → logout
//
// Penpot with OIDC via enable-login-with-oidc flag.
// The dashboard opens Penpot in a fullscreen iframe. Penpot shows the login page,
// user clicks the OIDC link → Keycloak login page loads inside the iframe →
// after login the iframe navigates back to the Penpot dashboard.
test("dashboard to penpot: admin sso login, verify ui, logout", async ({ page }) => {
  const expectedPenpotBaseUrl = penpotBaseUrl.replace(/\/$/, "");
  const expectedOidcAuthUrl = `${oidcIssuerUrl.replace(/\/$/, "")}/protocol/openid-connect/auth`;

  // Start from a deterministic unauthenticated state.
  await ensurePenpotLoggedOut(page, expectedPenpotBaseUrl);

  // 1. Navigate to dashboard with the Penpot login URL pre-loaded in the iframe.
  await page.goto(`/?iframe=${encodeURIComponent(expectedPenpotBaseUrl)}`);

  // 2. Wait for the iframe to appear
  await expect(page.locator("#main iframe")).toBeVisible({ timeout: 30_000 });

  // 3. Wait for the iframe to load Penpot
  await waitForFrameUrl(
    page.locator("#main iframe"),
    expectedPenpotBaseUrl,
    60_000,
    `Expected iframe to load Penpot at ${expectedPenpotBaseUrl}`
  );

  // 4. Find/click the OIDC login entry unless the iframe is already on Keycloak.
  const appFrame = page.frameLocator("#main iframe").first();
  const initialState = await waitForPenpotOidcEntry(
    page,
    page.locator("#main iframe"),
    appFrame,
    expectedPenpotBaseUrl,
    expectedOidcAuthUrl,
    60_000,
    "Timed out waiting for a Penpot OIDC login entry or Keycloak redirect"
  );

  if (initialState.kind === "penpot-oidc-entry") {
    await triggerPenpotOidcLogin(page, page.locator("#main iframe"), appFrame, expectedOidcAuthUrl);
  }

  // 5. After clicking OIDC, the iframe navigates to Keycloak.
  await waitForFrameUrl(
    page.locator("#main iframe"),
    expectedOidcAuthUrl,
    60_000,
    "Expected iframe to navigate to Keycloak for authentication"
  );

  // 6. Perform OIDC login with admin credentials
  const keycloakFrame = page.frameLocator("#main iframe").first();
  await performOidcLogin(keycloakFrame, adminUsername, adminPassword);

  // 7. Wait for navigation back to Penpot dashboard after authentication.
  await expect
    .poll(
      async () => {
        const iframeHandle = await page.locator("#main iframe").first().elementHandle();
        const frame = iframeHandle ? await iframeHandle.contentFrame() : null;
        const url = frame ? frame.url() : "";
        return url.includes(expectedPenpotBaseUrl) && !url.includes("/login");
      },
      {
        timeout: 60_000,
        message: "Expected iframe to navigate back to Penpot authenticated area"
      }
    )
    .toBe(true);

  // 8. Verify the user is authenticated (Penpot shows dashboard/projects)
  const penpotFrameAuth = page.frameLocator("#main iframe").first();
  await expect
    .poll(
      async () => await isPenpotAuthenticated(penpotFrameAuth),
      {
        timeout: 60_000,
        message: "Expected Penpot to show authenticated user interface"
      }
    )
    .toBe(true);

  // 9. Logout by navigating to /logout in the iframe
  await page.goto(`/?iframe=${encodeURIComponent(expectedPenpotBaseUrl + "/logout")}`);
  await page.waitForTimeout(2_000);

  // 10. Verify we're back on the Penpot login page (OIDC button visible again)
  await page.goto(`/?iframe=${encodeURIComponent(expectedPenpotBaseUrl)}`);
  const penpotFrameAfterLogout = page.frameLocator("#main iframe").first();
  await expect
    .poll(
      async () => Boolean(await findFirstVisible(getPenpotOidcEntryLocators(penpotFrameAfterLogout))),
      {
        timeout: 60_000,
        message: "Expected Penpot to return to login page after logout"
      }
    )
    .toBe(true);
});

// Scenario II: dashboard → Penpot iframe → SSO login as biber (regular user) → verify authenticated → logout
//
// Similar to admin test but verifies regular (non-admin) user SSO flow works.
test("dashboard to penpot: biber sso login, verify ui, logout", async ({ page }) => {
  const expectedPenpotBaseUrl = penpotBaseUrl.replace(/\/$/, "");
  const expectedOidcAuthUrl = `${oidcIssuerUrl.replace(/\/$/, "")}/protocol/openid-connect/auth`;

  // Start from a deterministic unauthenticated state.
  await ensurePenpotLoggedOut(page, expectedPenpotBaseUrl);

  // 1. Navigate to dashboard with the Penpot login URL pre-loaded in the iframe.
  await page.goto(`/?iframe=${encodeURIComponent(expectedPenpotBaseUrl)}`);

  // 2. Wait for the iframe to appear
  await expect(page.locator("#main iframe")).toBeVisible({ timeout: 30_000 });

  // 3. Wait for the iframe to load Penpot
  await waitForFrameUrl(
    page.locator("#main iframe"),
    expectedPenpotBaseUrl,
    60_000,
    `Expected iframe to load Penpot at ${expectedPenpotBaseUrl}`
  );

  // 4. Find/click the OIDC login entry unless the iframe is already on Keycloak.
  const appFrame = page.frameLocator("#main iframe").first();
  const initialState = await waitForPenpotOidcEntry(
    page,
    page.locator("#main iframe"),
    appFrame,
    expectedPenpotBaseUrl,
    expectedOidcAuthUrl,
    60_000,
    "Timed out waiting for a Penpot OIDC login entry or Keycloak redirect"
  );

  if (initialState.kind === "penpot-oidc-entry") {
    await triggerPenpotOidcLogin(page, page.locator("#main iframe"), appFrame, expectedOidcAuthUrl);
  }

  // 5. Wait for iframe to navigate to Keycloak
  await waitForFrameUrl(
    page.locator("#main iframe"),
    expectedOidcAuthUrl,
    60_000,
    "Expected iframe to navigate to Keycloak for authentication"
  );

  // 6. Perform OIDC login with biber credentials
  const keycloakFrame = page.frameLocator("#main iframe").first();
  await performOidcLogin(keycloakFrame, biberUsername, biberPassword);

  // 7. Wait for navigation back to Penpot dashboard.
  await expect
    .poll(
      async () => {
        const iframeHandle = await page.locator("#main iframe").first().elementHandle();
        const frame = iframeHandle ? await iframeHandle.contentFrame() : null;
        const url = frame ? frame.url() : "";
        return url.includes(expectedPenpotBaseUrl) && !url.includes("/login");
      },
      {
        timeout: 60_000,
        message: "Expected iframe to navigate back to Penpot authenticated area for biber"
      }
    )
    .toBe(true);

  // 8. Verify the user is authenticated
  const penpotFrameAuth = page.frameLocator("#main iframe").first();
  await expect
    .poll(
      async () => await isPenpotAuthenticated(penpotFrameAuth),
      {
        timeout: 60_000,
        message: "Expected Penpot to show authenticated user interface for biber"
      }
    )
    .toBe(true);

  // 9. Logout
  await page.goto(`/?iframe=${encodeURIComponent(expectedPenpotBaseUrl + "/logout")}`);
  await page.waitForTimeout(2_000);

  // 10. Verify we're back on the login page
  await page.goto(`/?iframe=${encodeURIComponent(expectedPenpotBaseUrl)}`);
  const penpotFrameAfterLogout = page.frameLocator("#main iframe").first();
  await expect
    .poll(
      async () => Boolean(await findFirstVisible(getPenpotOidcEntryLocators(penpotFrameAfterLogout))),
      {
        timeout: 60_000,
        message: "Expected Penpot to return to login page after biber logout"
      }
    )
    .toBe(true);
});
