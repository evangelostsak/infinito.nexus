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

const penpotBaseUrl = decodeDotenvQuotedValue(process.env.PENPOT_BASE_URL);
const keycloakIssuerUrl = decodeDotenvQuotedValue(process.env.KEYCLOAK_ISSUER_URL);
const keycloakLogoutUrl = decodeDotenvQuotedValue(process.env.KEYCLOAK_LOGOUT_URL);
const adminUsername = decodeDotenvQuotedValue(process.env.ADMIN_USERNAME);
const adminPassword = decodeDotenvQuotedValue(process.env.ADMIN_PASSWORD);
const biberUsername = decodeDotenvQuotedValue(process.env.BIBER_USERNAME);
const biberPassword = decodeDotenvQuotedValue(process.env.BIBER_PASSWORD);

test.beforeEach(() => {
  expect(penpotBaseUrl, "PENPOT_BASE_URL must be set in the Playwright env file").toBeTruthy();
  expect(keycloakIssuerUrl, "KEYCLOAK_ISSUER_URL must be set in the Playwright env file").toBeTruthy();
  expect(keycloakLogoutUrl, "KEYCLOAK_LOGOUT_URL must be set in the Playwright env file").toBeTruthy();
  expect(adminUsername, "ADMIN_USERNAME must be set in the Playwright env file").toBeTruthy();
  expect(adminPassword, "ADMIN_PASSWORD must be set in the Playwright env file").toBeTruthy();
  expect(biberUsername, "BIBER_USERNAME must be set in the Playwright env file").toBeTruthy();
  expect(biberPassword, "BIBER_PASSWORD must be set in the Playwright env file").toBeTruthy();
});

// Scenario 1: Dashboard → Penpot iframe (basic reachability test)
test("dashboard to penpot: endpoint reachable and landing page visible", async ({ page }) => {
  const expectedPenpotBaseUrl = penpotBaseUrl.replace(/\/$/, "");

  await page.goto(`/?iframe=${encodeURIComponent(expectedPenpotBaseUrl)}`);

  const iframe = page.locator("#main iframe").first();
  await expect(iframe).toBeVisible({ timeout: 60_000 });

  await expect
    .poll(
      async () => {
        const handle = await iframe.elementHandle();
        const frame = handle ? await handle.contentFrame() : null;

        if (!frame) {
          return "";
        }

        return frame.url();
      },
      {
        timeout: 60_000,
        message: "Expected dashboard iframe to load Penpot URL"
      }
    )
    .toContain(expectedPenpotBaseUrl);

  const penpotFrame = page.frameLocator("#main iframe").first();
  await expect(penpotFrame.locator("body")).toBeVisible({ timeout: 60_000 });

  const hasPenpotKeyword = await expect
    .poll(
      async () => {
        const text = (await penpotFrame.locator("body").innerText()).toLowerCase();
        return text.includes("penpot") || text.includes("login") || text.includes("sign in");
      },
      {
        timeout: 60_000,
        message: "Expected Penpot frame body to render login/landing content"
      }
    )
    .toBeTruthy();

  return hasPenpotKeyword;
});

// Scenario 2: Direct Penpot URL access - verify login page is displayed
test("penpot direct url: login page loads with SSO button", async ({ page }) => {
  const expectedPenpotBaseUrl = penpotBaseUrl.replace(/\/$/, "");

  await page.goto(expectedPenpotBaseUrl, { waitUntil: "domcontentloaded" });

  // Wait for login page to render
  await expect(page.locator("body")).toBeVisible({ timeout: 30_000 });

  // Verify login page is displayed - look for login form or SSO button
  const loginForm = page.locator("form, [role='form'], .login-form, [class*='login']").first();
  await expect(loginForm).toBeVisible({ timeout: 30_000 });

  // Look for SSO/Keycloak login button
  const ssoButton = page.locator(
    "button:has-text('SSO'), button:has-text('Keycloak'), button:has-text('Sign in with'), a:has-text('SSO')"
  ).first();

  // SSO button should be visible on the login page
  await expect(ssoButton).toBeVisible({ timeout: 30_000 });
});

// Helper function: Perform SSO login via Keycloak
async function performSSOLogin(page, baseUrl, username, password) {
  const expectedPenpotBaseUrl = baseUrl.replace(/\/$/, "");

  // Navigate to Penpot login page
  await page.goto(expectedPenpotBaseUrl, { waitUntil: "domcontentloaded" });

  // Click SSO/Keycloak login button
  const ssoButton = page.locator(
    "button:has-text('SSO'), button:has-text('Keycloak'), button:has-text('Sign in with'), a:has-text('SSO')"
  ).first();
  
  await ssoButton.click();

  // Playwright will follow the redirect to Keycloak
  // Wait for Keycloak login page to load
  await page.waitForURL(/.*keycloak.*|.*auth.*/, { timeout: 30_000 });

  // Wait for login form on Keycloak
  const usernameField = page.locator("input[name='username'], input[id*='username']").first();
  await usernameField.waitFor({ state: "visible", timeout: 30_000 });

  // Fill in credentials
  await usernameField.fill(username);

  const passwordField = page.locator("input[name='password'], input[type='password']").first();
  await passwordField.fill(password);

  // Click login button
  const loginButton = page.locator("button[type='submit'], button:has-text('Sign In'), button:has-text('Log In')").first();

  await Promise.all([
    page.waitForNavigation({ url: /.*penpot.*/, waitUntil: "domcontentloaded", timeout: 60_000 }).catch(() => {}),
    loginButton.click(),
  ]);
}

// Helper function: Verify authenticated session in Penpot
async function verifyPenpotAuthenticatedSession(page) {
  // Wait for dashboard/authenticated UI elements
  // Penpot shows user menu, projects, or workspace when authenticated
  const userMenuOrProjects = page.locator(
    "[class*='user'], [class*='profile'], [class*='dashboard'], [class*='projects'], a[href*='settings'], button[aria-label*='user']"
  ).first();

  await expect(userMenuOrProjects).toBeVisible({ timeout: 30_000 });
}

// Scenario 3: SSO login with admin user
test("penpot sso: admin user login and session verification", async ({ page }) => {
  const expectedPenpotBaseUrl = penpotBaseUrl.replace(/\/$/, "");

  // Perform SSO login with admin credentials
  await performSSOLogin(page, expectedPenpotBaseUrl, adminUsername, adminPassword);

  // Verify we're back at Penpot and authenticated
  await verifyPenpotAuthenticatedSession(page);

  // Verify we're on Penpot dashboard (URL should contain penpot base)
  await expect(page).toHaveURL(new RegExp(expectedPenpotBaseUrl.replace(/https?:\/\//, "")));

  // Logout via the universal logout endpoint
  await page.goto(`${expectedPenpotBaseUrl.replace(/\/$/, "")}/logout`, { 
    waitUntil: "commit" 
  }).catch(() => {});

  // Wait a moment for session cleanup
  await page.waitForTimeout(2000);

  // Verify we're logged out - return to login page
  await page.goto(expectedPenpotBaseUrl, { waitUntil: "domcontentloaded" });
  
  const loginForm = page.locator("form, [role='form'], .login-form, [class*='login']").first();
  await expect(loginForm).toBeVisible({ timeout: 30_000 });
});

// Scenario 4: SSO login with biber (standard) user
test("penpot sso: biber user login and session verification", async ({ page }) => {
  const expectedPenpotBaseUrl = penpotBaseUrl.replace(/\/$/, "");

  // Perform SSO login with biber credentials
  await performSSOLogin(page, expectedPenpotBaseUrl, biberUsername, biberPassword);

  // Verify we're back at Penpot and authenticated
  await verifyPenpotAuthenticatedSession(page);

  // Verify we're on Penpot dashboard
  await expect(page).toHaveURL(new RegExp(expectedPenpotBaseUrl.replace(/https?:\/\//, "")));

  // Logout via the universal logout endpoint
  await page.goto(`${expectedPenpotBaseUrl.replace(/\/$/, "")}/logout`, { 
    waitUntil: "commit" 
  }).catch(() => {});

  // Wait a moment for session cleanup
  await page.waitForTimeout(2000);

  // Verify we're logged out - return to login page
  await page.goto(expectedPenpotBaseUrl, { waitUntil: "domcontentloaded" });
  
  const loginForm = page.locator("form, [role='form'], .login-form, [class*='login']").first();
  await expect(loginForm).toBeVisible({ timeout: 30_000 });
});
