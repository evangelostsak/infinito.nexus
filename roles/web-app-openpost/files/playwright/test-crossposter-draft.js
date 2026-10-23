const { test, expect } = require("@playwright/test");
const { gotoOnion } = require("./personas");
const { resolveTimeout } = require("./timeouts");

async function crosspostedDraft(page, shared, headers) {
  for (const workspace of await shared.apiRequest(page, headers, "GET", "/workspaces")) {
    const drafts = await shared.apiRequest(
      page,
      headers,
      "GET",
      `/publications?workspace_id=${workspace.id}&status=draft&search=crossposterreview&limit=50`,
    );
    const found = (drafts || []).find((item) => (item.metadata || {}).crossposter_route === "ci-review");
    if (found) {
      return { workspace: workspace.id, publication: found };
    }
  }
  return null;
}

exports.register = function (shared) {
  test("administrator: finds a crossposted draft in the desk, edits it and schedules it", async ({ page }) => {
    shared.skipUnlessServiceEnabled("crossposter");
    shared.skipUnlessServiceEnabled("mastodon");
    test.setTimeout(resolveTimeout(300_000)); // draft lookup, composer autosave and the scheduling round-trip
    const label = "break-glass administrator";
    const edited = `Edited in the desk ${Date.now()}`;

    await shared.signInViaLocal(page, shared.env.breakglassEmail, shared.env.breakglassPassword, label);
    const headers = shared.apiSession();
    const found = await crosspostedDraft(page, shared, headers);
    expect(found, `${label}: the CLI run must leave a crossposted review draft`).toBeTruthy();
    const marker = String(found.publication.title || found.publication.source_text).split(" ")[1];

    await gotoOnion(page, `${shared.env.appBaseUrl}/publications?tab=drafts`, { waitUntil: "domcontentloaded" });
    await page.getByRole("textbox", { name: /search posts/i }).fill(marker);
    const listed = page.getByRole("link", { name: new RegExp(marker, "i") }).first();
    await expect(listed, `${label}: the crossposted draft must be listed among the drafts`).toBeVisible({
      timeout: resolveTimeout(60_000),
    });
    await listed.click();

    const text = page.getByRole("textbox", { name: /post text/i }).first();
    await expect(text, `${label}: the draft must open in the composer`).toBeVisible({ timeout: resolveTimeout(60_000) });
    await text.fill(edited);
    await page.getByRole("main").getByRole("button", { name: /^more$/i }).click();
    await page.getByRole("menuitem", { name: /^schedule$/i }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: /^in 3 hours$/i }).click();
    await dialog.getByRole("button", { name: /^schedule$/i }).click();

    await expect
      .poll(
        async () => {
          const current = await shared.apiRequest(page, headers, "GET", `/publications/${found.publication.id}`);
          return `${current.status}|${String(current.source_text).includes(edited)}`;
        },
        { timeout: resolveTimeout(60_000), message: `${label}: the edited draft must end scheduled` },
      )
      .toBe("scheduled|true");
    await shared.logout(page, label);
  });
};
