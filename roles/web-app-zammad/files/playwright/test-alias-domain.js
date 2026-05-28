const { test, expect, request } = require("@playwright/test");

exports.register = function (shared) {
  test("zammad alias domain maps to the canonical vhost (2xx direct OR 301-to-canonical)", async () => {
    const baseUrl = shared.env.zammadBaseUrl;
    expect(baseUrl, "ZAMMAD_BASE_URL must be set").toBeTruthy();

    const canonicalHost = baseUrl.replace(/^https?:\/\//, "").replace(/\/$/, "");
    const aliasHost = canonicalHost.replace(/^helpdesk\./, "zammad.helpdesk.");

    if (aliasHost === canonicalHost) {
      test.skip(true, "Alias hostname matches the canonical; nothing to assert.");
    }

    const aliasUrl = baseUrl.replace(/\/\/[^/]+/, `//${aliasHost}`);
    const api = await request.newContext({ ignoreHTTPSErrors: true, maxRedirects: 0 });
    const aliasResp = await api.get(aliasUrl, { maxRedirects: 0 }).catch((err) => err);

    const status = aliasResp.status?.();
    const isDirect2xx = typeof status === "number" && status >= 200 && status < 300;
    const isRedirectToCanonical = typeof status === "number" && status >= 300 && status < 400
      && (aliasResp.headers?.()["location"] || "").includes(canonicalHost);

    expect(
      isDirect2xx || isRedirectToCanonical,
      `Alias ${aliasUrl} must either serve 2xx directly (true vhost alias) or 30x-redirect to ${canonicalHost}. Got status=${status ?? aliasResp.message} location=${aliasResp.headers?.()["location"] ?? "<none>"}`
    ).toBe(true);

    await api.dispose();
  });
};
