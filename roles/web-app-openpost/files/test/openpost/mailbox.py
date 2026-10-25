"""Env (rendered into test.env from templates/test.env.j2):
OPENPOST_MAIL_HOST          IMAPS host of the platform mail server
OPENPOST_MAIL_PASSWORD_B64  base64 password of the administrator mailbox
"""

from __future__ import annotations

import base64
import imaplib
import os
import ssl

from openpost.api import MAIL_RECIPIENT, PROXY_ADDRESS

MAIL_HOST = os.environ["OPENPOST_MAIL_HOST"]
MAIL_PASSWORD = base64.b64decode(os.environ["OPENPOST_MAIL_PASSWORD_B64"]).decode()
IMAPS_PORT = 993
REPORT_SUBJECT = "OpenPost crossposter"


def reports_naming(urls: list[str]) -> list[str]:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    found: list[str] = []
    try:
        with imaplib.IMAP4_SSL(
            PROXY_ADDRESS or MAIL_HOST, IMAPS_PORT, ssl_context=context, timeout=60
        ) as imap:
            imap._encoding = "utf-8"
            imap.login(MAIL_RECIPIENT, MAIL_PASSWORD)
            imap.select("INBOX", readonly=True)
            for url in urls:
                typ, data = imap.search(
                    None, "SUBJECT", f'"{REPORT_SUBJECT}"', "BODY", f'"{url}"'
                )
                if typ == "OK" and data and data[0].split():
                    found.append(url)
    except (imaplib.IMAP4.error, OSError):
        return found
    return found
