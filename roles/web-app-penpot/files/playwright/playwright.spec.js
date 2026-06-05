const { test, expect } = require("@playwright/test");
const { skipUnlessServiceEnabled } = require("./service-gating");

const {
  decodeDotenvQuotedValue,
  normalizeBaseUrl,
  performKeycloakLoginForm,
  runAdminFlow,
  runBiberFlow,
  runGuestFlow,
} = require("./personas");
test.use({ ignoreHTTPSErrors: true });

const baseUrl = normalizeBaseUrl(process.env.PENPOT_BASE_URL || "");
const oidcIssuerUrl = normalizeBaseUrl(process.env.OIDC_ISSUER_URL || "");
const canonicalDomain = decodeDotenvQuotedValue(process.env.CANONICAL_DOMAIN || "");
const adminUsername = decodeDotenvQuotedValue(process.env.ADMIN_USERNAME);
const adminPassword = decodeDotenvQuotedValue(process.env.ADMIN_PASSWORD);
const adminEmail = decodeDotenvQuotedValue(process.env.ADMIN_EMAIL);
const biberUsername = decodeDotenvQuotedValue(process.env.BIBER_USERNAME);
const biberPassword = decodeDotenvQuotedValue(process.env.BIBER_PASSWORD);
const biberEmail = decodeDotenvQuotedValue(process.env.BIBER_EMAIL);

const loginRoute = (base) => `${base.replace(/\/$/, "")}/#/auth/login`;

// Penpot in-app OIDC (flavor: oidc): the login page renders an "OpenID"
// provider entry (clickable text, not a role=button) that redirects to
// Keycloak. Drive it, complete the Keycloak form, assert the round-trip
// returns to Penpot.
async function penpotOidcLogin(page, username, password) {
  const expectedAuth = `${oidcIssuerUrl}/protocol/openid-connect/auth`;
  const expectedBase = baseUrl.replace(/\/$/, "");
  await page.goto(loginRoute(baseUrl));
  const oidcEntry = page.getByText("OpenID", { exact: true });
  await expect(oidcEntry, "Expected a Penpot OpenID login entry").toBeVisible({ timeout: 60_000 });
  await oidcEntry.click();
  await expect
    .poll(() => page.url(), { timeout: 60_000, message: `expected redirect to ${expectedAuth}` })
    .toContain(expectedAuth);
  await performKeycloakLoginForm(page, username, password);
  await expect
    .poll(() => page.url(), { timeout: 90_000, message: `expected redirect back to ${expectedBase}` })
    .toContain(expectedBase);
  // Prove a real authenticated session: Penpot leaves the /auth/login route
  // for the dashboard/onboarding once the server-side token exchange succeeds.
  await expect
    .poll(() => page.url(), { timeout: 60_000, message: "expected to leave the login route after OIDC sign-in" })
    .not.toContain("/auth/login");
  await expect(page.locator("body")).toBeVisible({ timeout: 60_000 });
}

// Penpot LDAP: the login form exposes a dedicated "LDAP" submit button
// (disabled until the work-email + password fields are filled) that binds
// against OpenLDAP directly — no Keycloak round-trip.
async function penpotLdapLogin(page, email, password) {
  await page.goto(loginRoute(baseUrl));
  const emailField = page.getByLabel(/work email/i);
  const passwordField = page.getByLabel(/^password$/i);
  await expect(emailField, "Expected the Penpot login form").toBeVisible({ timeout: 60_000 });
  await emailField.fill(email);
  await passwordField.fill(password);
  const ldapButton = page.getByRole("button", { name: /^LDAP$/i });
  await expect(ldapButton, "Expected the LDAP submit button to enable once the form is filled").toBeEnabled({ timeout: 30_000 });
  await ldapButton.click();
  await expect
    .poll(() => page.url(), { timeout: 60_000, message: "expected to leave the login route after LDAP bind" })
    .not.toContain("/auth/login");
  await expect(page.locator("body")).toBeVisible({ timeout: 60_000 });
}

test.beforeEach(async ({ page }) => {
  expect(baseUrl, "PENPOT_BASE_URL must be set").toBeTruthy();
  expect(canonicalDomain, "CANONICAL_DOMAIN must be set").toBeTruthy();
  await page.context().clearCookies();
});

test("baseline: Penpot responds on the canonical domain with TLS", async ({ page }) => {
  const r = await page.goto(`${baseUrl}/`);
  expect(r, "Expected Penpot response").toBeTruthy();
  expect(r.status(), "Expected Penpot front page status < 500").toBeLessThan(500);
  expect(
    r.url().includes(canonicalDomain),
    `Expected canonical domain "${canonicalDomain}" to back the Penpot URL`,
  ).toBe(true);
  expect(r.headers()["strict-transport-security"], "Penpot must emit HSTS").toBeTruthy();
});

test("OIDC: administrator in-app provider button hands off to Keycloak and back (variant 0)", async ({ page }) => {
  skipUnlessServiceEnabled("sso");
  test.setTimeout(120_000); // OIDC round-trip + admin login form
  expect(adminUsername).toBeTruthy();
  expect(adminPassword).toBeTruthy();
  expect(oidcIssuerUrl).toBeTruthy();
  await penpotOidcLogin(page, adminUsername, adminPassword);
});

test("OIDC: biber non-admin RBAC user logs in via Keycloak (variant 0)", async ({ page }) => {
  skipUnlessServiceEnabled("sso");
  test.setTimeout(120_000); // OIDC round-trip + biber login form
  expect(biberUsername).toBeTruthy();
  expect(biberPassword).toBeTruthy();
  expect(oidcIssuerUrl).toBeTruthy();
  await penpotOidcLogin(page, biberUsername, biberPassword);
});

test("LDAP: administrator in-app form binds against OpenLDAP (variant 1)", async ({ page }) => {
  skipUnlessServiceEnabled("ldap");
  test.setTimeout(90_000); // LDAP bind + first authenticated render
  expect(adminEmail).toBeTruthy();
  expect(adminPassword).toBeTruthy();
  await penpotLdapLogin(page, adminEmail, adminPassword);
});

test("LDAP: biber non-admin RBAC user binds against OpenLDAP (variant 1)", async ({ page }) => {
  skipUnlessServiceEnabled("ldap");
  test.setTimeout(90_000); // LDAP bind + first authenticated render
  expect(biberEmail).toBeTruthy();
  expect(biberPassword).toBeTruthy();
  await penpotLdapLogin(page, biberEmail, biberPassword);
});

test("project: administrator creates a design project", async ({ page }) => {
  skipUnlessServiceEnabled("sso");
  test.setTimeout(120_000); // OIDC round-trip + dashboard project creation
  await penpotOidcLogin(page, adminUsername, adminPassword);
  const projectName = `pw-project-${Date.now()}`;
  const addProject = page
    .getByRole("button", { name: /new project|add project|create.*project/i })
    .or(page.locator('[data-testid="add-project"], [data-test="add-project"]'))
    .first();
  await expect(addProject, "Expected a create-project control on the dashboard").toBeVisible({ timeout: 60_000 });
  await addProject.click();
  const nameInput = page.locator('.project-name input, input[type="text"]:visible, [contenteditable="true"]:visible').first();
  await nameInput.fill(projectName);
  await nameInput.press("Enter");
  await expect(page.getByText(projectName, { exact: false }).first()).toBeVisible({ timeout: 30_000 });
});

test("asset: administrator uploads an image asset into a design file", async ({ page }) => {
  skipUnlessServiceEnabled("sso");
  test.setTimeout(180_000); // OIDC + editor load + image upload
  await penpotOidcLogin(page, adminUsername, adminPassword);

  // Open Drafts and create a new file; Penpot navigates into the workspace editor.
  await page.getByText("Drafts", { exact: true }).first().click();
  const newFile = page.getByText(/\+\s*New File/i).first();
  await expect(newFile, "Expected a create-file control in Drafts").toBeVisible({ timeout: 60_000 });
  await newFile.click();
  await expect.poll(() => page.url(), { timeout: 90_000, message: "expected to enter the Penpot workspace editor" })
    .toContain("/workspace");

  // Upload a small PNG into the file via the workspace image file input.
  const onePixelPng = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
    "base64",
  );
  const fileInput = page.locator('input[type="file"]').first();
  await fileInput.waitFor({ state: "attached", timeout: 60_000 });
  await fileInput.setInputFiles({ name: "pw-asset.png", mimeType: "image/png", buffer: onePixelPng });

  // The uploaded image becomes a board/shape on the canvas; assert Penpot
  // acknowledges the upload (a layer/element referencing the file appears).
  await expect(page.getByText(/pw-asset|image/i).first()).toBeVisible({ timeout: 60_000 });
});

// Persona scenarios.
// Bodies live in the shared helper roles/test-e2e-playwright/files/personas.
// Penpot's login is an in-app "OpenID" provider entry (clickable text, not a
// `login`/`sign-in` link) and its logout sits behind an SPA user menu the
// generic persona helper does not recognise, so the authenticated biber /
// administrator persona journeys are declared blocked here (mirrors
// web-app-taiga). Their real auth paths are exercised by the dedicated
// OIDC + LDAP scenarios above (both administrator and biber).

test("guest: public-landing → auth chain → never authenticated", async ({ page }) => {
  await runGuestFlow(page);
});

test("biber: app → role interaction → universal logout", async ({ page }) => {
  await runBiberFlow(page);
});

test("administrator: app → admin interaction → universal logout", async ({ page }) => {
  await runAdminFlow(page);
});
