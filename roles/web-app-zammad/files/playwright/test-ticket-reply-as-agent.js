const { test, expect, request } = require("@playwright/test");

async function seedTicketViaApi(baseUrl, adminApiUsername, adminApiPassword, subject) {
  const api = await request.newContext({
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: {
      Authorization: `Basic ${Buffer.from(`${adminApiUsername}:${adminApiPassword}`).toString("base64")}`,
      "Content-Type": "application/json",
    },
  });

  const resp = await api.post(`${baseUrl}/api/v1/tickets`, {
    data: {
      title: subject,
      group: "Users",
      customer: adminApiUsername,
      article: {
        subject,
        body: "Seed article for the agent-reply Playwright scenario.",
        type: "note",
        internal: false,
      },
    },
  });

  if (resp.status() >= 300) {
    throw new Error(`Seed POST /api/v1/tickets failed: ${resp.status()} ${await resp.text()}`);
  }
  const ticket = await resp.json();
  await api.dispose();
  return ticket;
}

exports.register = function (shared) {
  test("administrator (agent): replies to an API-seeded ticket via the SPA", async ({ page }) => {
    expect(shared.env.adminApiUsername, "ADMIN_API_USERNAME must be set").toBeTruthy();
    expect(shared.env.adminApiPassword, "ADMIN_API_PASSWORD must be set").toBeTruthy();

    const subject = `playwright-agent-reply-${Date.now()}`;
    const ticket = await seedTicketViaApi(
      shared.env.zammadBaseUrl,
      shared.env.adminApiUsername,
      shared.env.adminApiPassword,
      subject
    );

    await shared.signInAsApiBot(page);
    await page.goto(`${shared.env.zammadBaseUrl}/#ticket/zoom/${ticket.id}`, { waitUntil: "domcontentloaded" });
    await expect(page.locator("body")).toContainText(subject, { timeout: 60_000 });

    // Scope the contenteditable lookup to Zammad's article-create area
    // (`.article-add`) so the .first() doesn't hit the ticket-title field.
    const replyText = `agent-reply ${Date.now()}`;
    const replyBody = page.locator('.article-add [contenteditable="true"]').first();
    await replyBody.waitFor({ state: "visible", timeout: 60_000 });
    await replyBody.click();
    await page.keyboard.type(replyText);

    // The "Update" button lives in the same .article-add panel; pin it
    // there too to avoid clicking unrelated update controls.
    await page.locator('.article-add').getByRole("button", { name: /update|aktualisieren/i }).first().click();

    await expect(page.locator("body")).toContainText(replyText, { timeout: 60_000 });

    await shared.zammadLogout(page);
  });
};
