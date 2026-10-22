"""Env (rendered into test.env from templates/test.env.j2):
    OPENPOST_LOCAL_URL           published OpenPost origin on the stack host
    OPENPOST_API_HEADERS_B64     base64 JSON of the Host and proto headers the proxy would send
    OPENPOST_ADMIN_EMAIL         break-glass instance admin e-mail
    OPENPOST_ADMIN_PASSWORD_B64  base64 break-glass password
    OPENPOST_RELAY_TARGETS       JSON map of sibling platform to the domain the relay carries
    OPENPOST_DEADLINE_SECONDS    readiness budget, below the harness timeout
    OPENPOST_PUBLIC_URL          public origin served by the shared proxy
    OPENPOST_SSO_ENABLED         true when Keycloak provisions users, so the proxy closes password sign-up
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ["OPENPOST_LOCAL_URL"].rstrip("/") + "/api/v1"
HEADERS = json.loads(base64.b64decode(os.environ["OPENPOST_API_HEADERS_B64"]))
ADMIN_EMAIL = os.environ["OPENPOST_ADMIN_EMAIL"]
ADMIN_PASSWORD = base64.b64decode(os.environ["OPENPOST_ADMIN_PASSWORD_B64"]).decode()
RELAY_TARGETS = json.loads(os.environ["OPENPOST_RELAY_TARGETS"])
DEADLINE = time.monotonic() + int(os.environ["OPENPOST_DEADLINE_SECONDS"])
PUBLIC_URL = os.environ["OPENPOST_PUBLIC_URL"].rstrip("/")
SSO_ENABLED = os.environ["OPENPOST_SSO_ENABLED"] == "true"

PRIVATE_TARGETS = ("https://postgres", "https://10.0.0.1")

failures: list[str] = []


def call(method: str, path: str, body: object = None, token: str = "") -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method)
    for name, value in HEADERS.items():
        request.add_header(name, value)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode()
            status = response.status
    except urllib.error.HTTPError as error:
        raw = error.read().decode()
        status = error.code
    try:
        return status, json.loads(raw) if raw else None
    except ValueError:
        return status, raw


def check(label: str, ok: bool, detail: object = "") -> None:
    print(("[OK]   " if ok else "[FAIL] ") + label + (f": {detail}" if not ok and detail else ""))
    if not ok:
        failures.append(label)


def wait_ready() -> None:
    while True:
        try:
            status, _ = call("GET", "/ready")
            if status == 200:
                return
        except OSError:
            pass
        if time.monotonic() > DEADLINE:
            sys.exit("[FAIL] OpenPost never reported ready")
        time.sleep(5)


def login() -> str:
    status, body = call("POST", "/auth/login", {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if status != 200 or not isinstance(body, dict) or not body.get("token"):
        sys.exit(f"[FAIL] break-glass login returned HTTP {status}")
    print("[OK]   break-glass instance admin signs in")
    return str(body["token"])


def flag(path: str, key: str, token: str = "") -> object:
    status, body = call("GET", path, token=token)
    if status != 200 or not isinstance(body, dict):
        return f"HTTP {status}"
    return body.get(key)


def public_status(method: str, path: str) -> int:
    request = urllib.request.Request(PUBLIC_URL + path, data=b"{}", method=method)
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def check_data_minimisation(token: str) -> None:
    for label, path, key in (
        ("PostHog telemetry is off", "/telemetry/config", "enabled"),
        ("diagnostics reports are off", "/diagnostics/public-config", "enabled"),
        ("public profiles are off", "/auth/config", "public_profiles_enabled"),
    ):
        value = flag(path, key)
        check(label, value is False, f"{path} {key}={value!r}")
    if SSO_ENABLED:
        status = public_status("POST", "/api/v1/auth/register")
        check("the proxy refuses password self-registration", status == 403, f"HTTP {status}")
    else:
        value = flag("/auth/config", "registration_enabled")
        check("password self-registration is off", value is False, f"registration_enabled={value!r}")


def workspace_id(token: str) -> str:
    status, body = call("GET", "/workspaces", token=token)
    if status == 200 and isinstance(body, list) and body:
        return str(body[0]["id"])
    status, body = call("POST", "/workspaces", {"name": "CLI probe"}, token=token)
    if status != 200 or not isinstance(body, dict):
        sys.exit(f"[FAIL] cannot create a probe workspace: HTTP {status}")
    return str(body["id"])


def auth_url(token: str, workspace: str, platform: str, instance_url: str) -> tuple[int, object]:
    query = urllib.parse.urlencode({"workspace_id": workspace, "instance_url": instance_url})
    return call("GET", f"/accounts/{platform}/auth-url?{query}", token=token)


def check_relay(token: str, workspace: str) -> None:
    for platform, domain in RELAY_TARGETS.items():
        if platform == "peertube":
            continue
        status, body = auth_url(token, workspace, platform, f"https://{domain}")
        check(f"relay carries {platform} at {domain} past the guard", status == 200, f"HTTP {status} {body}")
    for target in PRIVATE_TARGETS:
        status, body = auth_url(token, workspace, "mastodon", target)
        check(f"guard still rejects {target}", status != 200, f"HTTP {status} {body}")


def main() -> int:
    wait_ready()
    print("[OK]   /api/v1/ready answers 200")
    token = login()
    check_data_minimisation(token)
    workspace = workspace_id(token)
    check_relay(token, workspace)
    if failures:
        print(f"[FAIL] {len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
