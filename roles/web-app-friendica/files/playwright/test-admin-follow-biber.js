const { test, expect } = require("@playwright/test");

// Administrator follows biber on friendica.
//
// Exercises the local-instance follow path: the administrator logs in
// via the variant-appropriate flow (v0 double-login through Keycloak,
// v2 native /login form), opens biber's profile page, triggers the
// follow / connect action, and confirms biber appears in the
// administrator's contact list afterwards.
//
// Friendica's UI labels the action "Connect/Follow", "Follow" (English),
// or "Verbinden/Folgen" / "Folgen" (German), depending on theme + locale.
// The actual handler is `/contact/follow?url=<profile-url>`, which renders
// a confirmation form. POST-ing that form 302-redirects to
// `/contact/<numeric-id>` once friendica has persisted the local contact
// row — that redirect is what verifies the follow took effect. (The
// global /contact listing only shows approved follows by default and
// would skip the pending row even after a successful POST.)

exports.register = function (shared) {
  test("friendica: administrator can follow biber", async ({ browser }) => {
    shared.skipUnlessServiceEnabled("ldap");

    await shared.provisionBiberAccount(browser);

    const baseUrl = shared.trimmedBaseUrl();
    const login = shared.pickLoginPath();

    const adminContext = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      const adminPage = await adminContext.newPage();
      await login(adminPage, shared.env.adminUsername, shared.env.adminPassword);

      // Drive the follow via friendica's documented HTTP entry point so
      // the test stays stable across themes and locales. Anchor links
      // labelled "Connect/Follow" on the profile page all resolve to the
      // same /contact/follow handler, which renders a confirmation form.
      const followEntryUrl = `${baseUrl}/contact/follow?url=${encodeURIComponent(`${baseUrl}/profile/${shared.env.biberUsername}`)}`;
      await adminPage.goto(followEntryUrl, { waitUntil: "domcontentloaded" });

      const expectedHandle = `${shared.env.biberUsername}@${new URL(baseUrl).host}`;

      // Friendica's confirmation form has a unique submit element
      // (id="dfrn-request-submit-button", value="Submit request"). The
      // navbar search form appears earlier in the document so a generic
      // form.first() selector would hit the wrong target.
      //
      // The suite runs twice against one persistent instance (sync + async
      // deploy passes). On the second pass biber is already a contact, so
      // /contact/follow short-circuits to an "already added this contact"
      // page that carries no submit button but still renders biber's
      // identity address. Wait for either surface and only POST the form
      // when it is the fresh-follow confirmation.
      const submitButton = adminPage.locator("#dfrn-request-submit-button");
      const biberHandle = adminPage.getByText(expectedHandle, { exact: false });
      await expect(submitButton.or(biberHandle).first()).toBeVisible({ timeout: 60_000 });

      if (await submitButton.isVisible()) {
        await Promise.all([
          adminPage.waitForLoadState("domcontentloaded"),
          submitButton.click(),
        ]);

        // A successful follow 302-redirects to /contact/<numeric-id> — the
        // detail page of the freshly-persisted local contact row.
        await expect
          .poll(() => adminPage.url(), {
            timeout: 60_000,
            message: "Expected /contact/follow POST to land on /contact/<id> after persisting biber as a contact",
          })
          .toMatch(/\/contact\/\d+(?:[/?#]|$)/);
      }

      // Both the fresh /contact/<id> detail page and the idempotent "already
      // added" page render biber's identity address (nick@host); assert it as
      // the canonical post-follow proof.
      await expect(
        adminPage.locator("body"),
        `Expected biber's handle "${expectedHandle}" after follow`
      ).toContainText(expectedHandle, { timeout: 30_000 });
    } finally {
      await adminContext.close().catch(() => {});
    }
  });
};
