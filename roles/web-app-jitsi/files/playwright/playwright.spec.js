const { test, expect } = require("@playwright/test");
const { skipUnlessServiceEnabled } = require("./service-gating");
const {
  decodeDotenvQuotedValue,
  normalizeBaseUrl,
  runGuestFlow,
  runBiberFlow,
  runAdminFlow,
} = require("./personas");

test.use({ ignoreHTTPSErrors: true });

const appBaseUrl = normalizeBaseUrl(process.env.APP_BASE_URL || "");
const canonicalDomain = decodeDotenvQuotedValue(process.env.CANONICAL_DOMAIN);

// Drive the Jitsi Meet pre-join chrome for an authenticated persona: navigate
// to a room URL and wait for the SPA's prejoin lobby to render. The spec MUST
// NOT actually start a media call (the headless Playwright runner has no
// camera permission) but reaching the prejoin lobby behind the oauth2-proxy
// gate proves the user is on the role's authenticated surface.
async function reachJitsiPrejoin(page, personaLabel, roomSuffix) {
  const roomName = `e2e-${personaLabel}-${roomSuffix}`.toLowerCase().replace(/[^a-z0-9-]/g, "");
  await page.goto(`${appBaseUrl}/${roomName}`, { waitUntil: "domcontentloaded" });
  const prejoin = page
    .getByRole("button", { name: /join meeting|join|beitreten/i })
    .or(page.locator('[data-testid="prejoin.joinMeeting"], #premeeting-screen'))
    .first();
  await expect(prejoin, `${personaLabel}: prejoin surface must render`).toBeVisible({
    timeout: 60_000,
  });
  await expect
    .poll(() => page.url(), {
      timeout: 30_000,
      message: `${personaLabel}: URL must include the room path`,
    })
    .toContain(`/${roomName}`);
}

// Open the prejoin "more options" / Settings panel so the admin scenario lands
// on a surface that biber does NOT exercise. Jitsi exposes a Settings link in
// the prejoin and in-meeting toolbar; presence of the panel satisfies the
// "admin authorisation: Settings link visible in the DOM" rule from the
// per-role playwright contract.
async function openJitsiSettingsPanel(page, personaLabel) {
  const settingsTrigger = page
    .getByRole("button", { name: /settings|einstellungen|more options|optionen/i })
    .or(page.locator('[aria-label*="settings" i], [aria-label*="einstellungen" i], [data-testid*="settings" i]'))
    .first();
  await expect(
    settingsTrigger,
    `${personaLabel}: a Settings / More-options control must be visible in the DOM`,
  ).toBeVisible({ timeout: 30_000 });
}

test("guest: public-landing → auth chain → never authenticated", async ({ page }) => {
  await runGuestFlow(page);
});

test("biber: app → keycloak → join Jitsi room → logout", async ({ page }) => {
  test.setTimeout(180_000);
  await runBiberFlow(page, {
    biberInteraction: async (p) => {
      await reachJitsiPrejoin(p, "biber", "biber-room");
    },
  });
});

test("administrator: app → keycloak → settings panel → logout", async ({ page }) => {
  test.setTimeout(180_000);
  await runAdminFlow(page, {
    adminInteraction: async (p) => {
      await reachJitsiPrejoin(p, "admin", "admin-room");
      await openJitsiSettingsPanel(p, "administrator");
    },
  });
});

// Dedicated LDAP scenario per the playwright contract: when both OIDC and LDAP
// are enabled, each persona's primary login path uses OIDC, and each persona
// MUST additionally execute an LDAP-bound scenario. In V1 Keycloak federates
// OpenLDAP via the LDAP provider, so the form login still hits Keycloak's UI
// but the user record resolves through the LDAP backend.
test("biber: ldap-bound login through keycloak", async ({ page }) => {
  skipUnlessServiceEnabled("ldap");
  test.setTimeout(180_000);
  await runBiberFlow(page, {
    biberInteraction: async (p) => {
      await reachJitsiPrejoin(p, "biber", "biber-ldap-room");
    },
  });
});

test("administrator: ldap-bound login through keycloak", async ({ page }) => {
  skipUnlessServiceEnabled("ldap");
  test.setTimeout(180_000);
  await runAdminFlow(page, {
    adminInteraction: async (p) => {
      await reachJitsiPrejoin(p, "admin", "admin-ldap-room");
      await openJitsiSettingsPanel(p, "administrator");
    },
  });
});

// Baseline: canonical landing reachable + emits a CSP response header.
test("jitsi: canonical landing reachable + CSP header", async ({ page }) => {
  const response = await page.goto(`${appBaseUrl}/`, { waitUntil: "domcontentloaded" });
  expect(response, "jitsi landing response").toBeTruthy();
  expect(
    page.url().includes(canonicalDomain),
    `canonical domain ${canonicalDomain} backs the response URL`,
  ).toBe(true);
  expect(
    response.headers()["content-security-policy"],
    "jitsi canonical landing MUST emit a Content-Security-Policy header",
  ).toBeTruthy();
});
