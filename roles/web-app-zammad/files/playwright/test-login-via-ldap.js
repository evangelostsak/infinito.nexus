const { test, expect } = require("@playwright/test");

exports.register = function (shared) {
  test("biber (ldap): regular sign-in form authenticates against svc-db-openldap", async ({ page }) => {
    shared.skipUnlessServiceEnabled("ldap");
    if (shared.env.oidcEnabled) {
      test.skip(true, "OIDC also enabled — LDAP-form login only exercised in LDAP-only variant (V3)");
    }
    expect(shared.env.biberUsername, "BIBER_USERNAME must be set").toBeTruthy();
    expect(shared.env.biberPassword, "BIBER_PASSWORD must be set").toBeTruthy();

    await page.context().clearCookies();
    await page.goto(`${shared.env.zammadBaseUrl}/#login`, { waitUntil: "domcontentloaded" });

    // Zammad's #login route renders a <form> with concrete `name="username"`
    // and `name="password"` inputs plus a submit-button.
    const usernameInput = page.locator('input[name="username"]');
    const passwordInput = page.locator('input[name="password"]');
    await usernameInput.waitFor({ state: "visible", timeout: 60_000 });

    await usernameInput.fill(shared.env.biberUsername);
    await passwordInput.fill(shared.env.biberPassword);
    await page.locator('button[type="submit"]').first().click();

    // After successful LDAP auth Zammad's SPA mounts the user menu containing
    // the username — wait for it as proof-of-auth instead of grepping body
    // text (which can briefly contain login-page strings after submit).
    await expect(
      page.locator(`text=${shared.env.biberUsername}`).first(),
    ).toBeVisible({ timeout: 60_000 });

    await shared.zammadLogout(page);
  });
};
