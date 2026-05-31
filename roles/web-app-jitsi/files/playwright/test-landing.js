const { test, expect } = require("@playwright/test");

exports.register = function (shared) {
  test("jitsi: canonical landing reachable + CSP header", async ({ page }) => {
    const response = await page.goto(`${shared.env.appBaseUrl}/`, {
      waitUntil: "domcontentloaded",
    });
    expect(response, "jitsi landing response").toBeTruthy();
    expect(
      page.url().includes(shared.env.canonicalDomain),
      `canonical domain ${shared.env.canonicalDomain} backs the response URL`,
    ).toBe(true);
    expect(
      response.headers()["content-security-policy"],
      "jitsi canonical landing MUST emit a Content-Security-Policy header",
    ).toBeTruthy();
  });
};
