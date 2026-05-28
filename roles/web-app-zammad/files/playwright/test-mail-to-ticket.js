const { test, expect, request } = require("@playwright/test");
const tls = require("tls");
const net = require("net");

const { decodeDotenvQuotedValue } = require("./personas");

const mailEnabled    = (decodeDotenvQuotedValue(process.env.EMAIL_SERVICE_ENABLED || "false") || "false").toLowerCase() === "true";
const smtpHost       = decodeDotenvQuotedValue(process.env.MAIL_SMTP_HOST || "");
const smtpPort       = Number(decodeDotenvQuotedValue(process.env.MAIL_SMTP_PORT || "0")) || 0;
const smtpUser       = decodeDotenvQuotedValue(process.env.MAIL_SMTP_USER || "");
const smtpPass       = decodeDotenvQuotedValue(process.env.MAIL_SMTP_PASS || "");
const helpdeskAddr   = decodeDotenvQuotedValue(process.env.HELPDESK_EMAIL || "");

// Minimal SMTP submission client. Pure stdlib. Logs each transition to
// stderr so a hang surfaces the exact stage rather than a generic
// "SMTP timeout" — this matters because we're running inside the
// Playwright runner where socket behavior has historically been
// opaque (see previous skip note).
async function smtpSend({ host, port, user, pass, from, to, subject, body }) {
  return new Promise((resolve, reject) => {
    const wantAuth = Boolean(user && pass);
    const useImplicitTls = port === 465;
    const lines = []; // collected server output for diagnostics
    let buf = "";
    let stage = "connecting";
    const settled = { done: false };
    const trace = (msg) => process.stderr.write(`[smtp] ${msg}\n`);
    const fail = (err) => {
      if (settled.done) return;
      settled.done = true;
      trace(`FAIL stage=${stage} reason=${err.message} collected=${JSON.stringify(lines)}`);
      try { sock?.destroy(); } catch { /* ignore */ }
      reject(new Error(`SMTP fail at stage=${stage}: ${err.message}; server lines: ${JSON.stringify(lines)}`));
    };
    const ok = () => {
      if (settled.done) return;
      settled.done = true;
      trace("DONE");
      try { sock?.end(); } catch { /* ignore */ }
      resolve();
    };

    const consume = (code) => {
      const idx = buf.split(/\r?\n/).findIndex((line) => line.startsWith(`${code} `));
      if (idx >= 0) {
        buf = "";
        return true;
      }
      return false;
    };

    const transitions = {
      banner: () => { if (consume(220)) { stage = "ehlo"; trace(`>> EHLO`); sock.write(`EHLO playwright.infinito.example\r\n`); } },
      ehlo:   () => { if (consume(250)) {
        if (wantAuth) { stage = "auth"; trace(`>> AUTH LOGIN`); sock.write(`AUTH LOGIN\r\n`); }
        else          { stage = "mailfrom"; trace(`>> MAIL FROM (no-auth path)`); sock.write(`MAIL FROM:<${from}>\r\n`); }
      } },
      auth:   () => { if (consume(334)) { stage = "user"; trace(`>> user-b64`); sock.write(`${Buffer.from(user).toString("base64")}\r\n`); } },
      user:   () => { if (consume(334)) { stage = "pass"; trace(`>> pass-b64`); sock.write(`${Buffer.from(pass).toString("base64")}\r\n`); } },
      pass:   () => { if (consume(235)) { stage = "mailfrom"; trace(`>> MAIL FROM`); sock.write(`MAIL FROM:<${from}>\r\n`); } },
      mailfrom: () => { if (consume(250)) { stage = "rcptto"; trace(`>> RCPT TO`); sock.write(`RCPT TO:<${to}>\r\n`); } },
      rcptto: () => { if (consume(250)) { stage = "data"; trace(`>> DATA`); sock.write(`DATA\r\n`); } },
      data:   () => { if (consume(354)) {
        stage = "body";
        trace(`>> body+terminator`);
        const msg =
          `From: ${from}\r\n` +
          `To: ${to}\r\n` +
          `Subject: ${subject}\r\n` +
          `MIME-Version: 1.0\r\n` +
          `Content-Type: text/plain; charset=UTF-8\r\n` +
          `\r\n${body}\r\n.\r\n`;
        sock.write(msg);
      } },
      body:   () => { if (consume(250)) { stage = "quit"; trace(`>> QUIT`); sock.write(`QUIT\r\n`); } },
      quit:   () => { if (consume(221)) ok(); },
    };

    const handleData = (chunk) => {
      buf += chunk;
      lines.push(chunk.trimEnd());
      trace(`<< stage=${stage} chunk=${JSON.stringify(chunk.trimEnd()).slice(0, 200)}`);
      const handler = transitions[stage];
      if (!handler) { fail(new Error(`unknown stage ${stage}`)); return; }
      handler();
    };

    trace(`connecting ${useImplicitTls ? "tls" : "tcp"}://${host}:${port}`);
    let sock;
    if (useImplicitTls) {
      sock = tls.connect({ host, port, servername: host, rejectUnauthorized: false }, () => {
        stage = "banner";
        trace("tls-connected, awaiting banner");
      });
    } else {
      sock = net.connect({ host, port }, () => {
        stage = "banner";
        trace("tcp-connected, awaiting banner");
      });
    }
    sock.setEncoding("utf8");
    sock.setTimeout(30_000, () => fail(new Error(`socket inactivity timeout (30s)`)));
    sock.on("data", handleData);
    sock.on("error", (e) => fail(new Error(`socket error: ${e.message}`)));
    sock.on("close", () => {
      if (!settled.done) fail(new Error(`socket closed mid-conversation`));
    });
  });
}

exports.register = function (shared) {
  test("mail-to-ticket: SMTP send to helpdesk mailbox creates a Zammad ticket", async () => {
    test.skip(!mailEnabled, "Email service disabled in this variant");
    expect(smtpHost,     "MAIL_SMTP_HOST must be set when EMAIL_SERVICE_ENABLED=true").toBeTruthy();
    expect(smtpPort,     "MAIL_SMTP_PORT must be set").toBeTruthy();
    expect(smtpUser,     "MAIL_SMTP_USER must be set").toBeTruthy();
    expect(smtpPass,     "MAIL_SMTP_PASS must be set").toBeTruthy();
    expect(helpdeskAddr, "HELPDESK_EMAIL must be set").toBeTruthy();
    expect(shared.env.adminApiUsername, "ADMIN_API_USERNAME must be set").toBeTruthy();
    expect(shared.env.adminApiPassword, "ADMIN_API_PASSWORD must be set").toBeTruthy();

    const subject = `playwright-mail-${Date.now()}`;
    await smtpSend({
      host: smtpHost,
      port: smtpPort,
      user: smtpUser,
      pass: smtpPass,
      from: smtpUser,
      to: helpdeskAddr,
      subject,
      body: "Email body from the Infinito.Nexus Playwright mail-to-ticket regression test.",
    });

    const api = await request.newContext({
      ignoreHTTPSErrors: true,
      extraHTTPHeaders: {
        Authorization: `Basic ${Buffer.from(`${shared.env.adminApiUsername}:${shared.env.adminApiPassword}`).toString("base64")}`,
      },
    });

    // Force-fetch the IMAP inbound channel so we don't wait for the polling interval.
    const channelsResp = await api.get(`${shared.env.zammadBaseUrl}/api/v1/channels`);
    if (channelsResp.ok()) {
      const channels = await channelsResp.json();
      const emailChannel = channels.find?.((c) => c.area === "Email::Account");
      if (emailChannel) {
        await api.post(`${shared.env.zammadBaseUrl}/api/v1/channels/email_verify`, {
          data: { id: emailChannel.id, inbound: emailChannel.options?.inbound },
        }).catch(() => { /* best-effort */ });
      }
    }

    const deadline = Date.now() + 120_000;
    let found = null;
    while (Date.now() < deadline) {
      const searchResp = await api.get(
        `${shared.env.zammadBaseUrl}/api/v1/tickets/search?query=${encodeURIComponent(subject)}`
      );
      if (searchResp.ok()) {
        const result = await searchResp.json();
        const ids = Object.keys(result.assets?.Ticket ?? {});
        if (ids.length) { found = ids[0]; break; }
      }
      await new Promise((r) => setTimeout(r, 5_000));
    }

    await api.dispose();
    expect(found, `Expected a Zammad ticket with subject "${subject}" within 120s after SMTP send`).toBeTruthy();
  });
};
