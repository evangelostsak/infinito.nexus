const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test("addon account: Accounting/Invoicing module is installed and its action loads", async ({ browser }) => {
  skipUnlessAddonEnabled("account");
  test.setTimeout(120_000);

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToOdoo(page);
    await shared.openModule(page, "odoo/accounting");

    const errorSurface = page.locator(".o_error_dialog, .o_action_manager .o_nocontent_help_error");
    await expect(
      errorSurface,
      "opening the Accounting action must not raise an Odoo error dialog; if 'account' is enabled but the module is not installed, the action route 404s/errors and this asserts the failure instead of passing on a bare web-client shell"
    ).toHaveCount(0);

    const accountingApp = page
      .locator(".o_main_navbar .o_menu_brand")
      .filter({ hasText: /accounting|invoicing/i })
      .or(page.getByRole("button", { name: /^(accounting|invoicing)$/i }))
      .or(page.locator('.o_main_navbar [data-menu-xmlid*="account"]'))
      .first();
    await expect(
      accountingApp,
      "the Accounting/Invoicing app brand must render in the navbar — this proves the upstream 'account' module is actually installed and its menu is registered, not merely that a generic Odoo web-client shell rendered. When 'account' is enabled but the module failed to install/load, this is absent and the test MUST fail here, not pass on generic chrome."
    ).toBeVisible({ timeout: 60_000 });

    const accountingMenus = page
      .getByRole("menuitem", { name: /customers|vendors|customer invoices|bills|chart of accounts|journal/i })
      .or(page.getByText(/customer invoices|vendor bills|chart of accounts/i))
      .first();
    await expect(
      accountingMenus,
      "an Accounting-specific top menu (Customers/Vendors/Chart of Accounts/Journals) must be reachable — these views exist only because the 'account' module registered them, distinguishing a working Accounting install from an empty Odoo surface"
    ).toBeVisible({ timeout: 60_000 });
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
