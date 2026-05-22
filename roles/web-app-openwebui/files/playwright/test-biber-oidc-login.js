const { test, expect } = require("@playwright/test");

const { expectNoCspViolations } = require("./personas");
const { skipUnlessServiceEnabled } = require("./service-gating");

exports.register = function (shared) {
  test("biber: openwebui OIDC login and logout", async ({ page }) => {
    skipUnlessServiceEnabled("oidc");
    const diagnostics = shared.attachDiagnostics(page);

    await shared.signInViaDashboardOidc(
      page,
      shared.env.biberUsername,
      shared.env.biberPassword,
      "biber"
    );

    await expect(page.locator("body")).toContainText(
      /new chat|chat|welcome|sign|prompt/i,
      { timeout: 60_000 }
    );

    await shared.expectSignInRequiredAfterLogout(page);

    await expectNoCspViolations(page, diagnostics, "openwebui biber OIDC");
  });
};
