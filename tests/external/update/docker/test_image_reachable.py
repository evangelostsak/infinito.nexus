"""Check that every Docker image pin in roles/*/meta/services.yml resolves.

For each ``<service>.image`` + ``<service>.version`` pair discovered by
:func:`utils.docker.image.discovery.iter_role_images` we probe the
Docker Registry v2 manifest endpoint over plain HTTPS:

    HEAD https://<api-host>/v2/<name>/manifests/<tag>

Bearer-token negotiation (RFC 6750 + the Docker token spec) covers the
``401 + WWW-Authenticate: Bearer`` challenge that docker.io, ghcr.io,
quay.io and mcr.microsoft.com all speak. Skopeo is not required, which
matters because the compose test container does not ship it.

This is the gap closed against
:mod:`tests.external.update.docker.test_image_versions`, which compares
*outdated* versions but silently skips any pin that isn't semver-shaped
(``latest``, ``stable``, branch tags, …). Such pins were never probed
for existence, so a broken upstream tag like
``nfrastack/fusiondirectory:latest`` (no such tag published) only
surfaced at mirror-time.

Outcome classification:

* HTTP 200 / 202 / 206                              → reachable (silent)
* HTTP 404 manifest                                 → **fail** (broken pin)
* HTTP 401 / 403 / 429 / 4xx-other / 5xx / network  → warning, never fail

Suppress a check with ``# nocheck: docker-reachable`` directly above (or
on) the ``version:`` key for the service. See
``docs/contributing/actions/testing/suppression.md``.
"""

from __future__ import annotations

import concurrent.futures
import os
import re
import sys
import time
import unittest
from dataclasses import dataclass
from typing import TYPE_CHECKING

import requests

from utils.annotations.message import error, warning
from utils.docker.image.discovery import iter_role_images
from utils.roles.mapping import ROLE_FILE_META_SERVICES
from utils.update.docker import suppressed_services

from . import PROJECT_ROOT

if TYPE_CHECKING:
    from pathlib import Path

_REPO_ROOT = PROJECT_ROOT
_MAX_WORKERS = int(os.environ["INFINITO_WORKER_FETCH"])
# Per-request HTTP timeout (one HEAD / one token GET).
_REQUEST_TIMEOUT_SECONDS = 15
# Per-probe budget: at most 4 HTTP calls (HEAD, challenge HEAD, token GET,
# retried HEAD). Hard ceiling so a stuck registry never holds a worker forever.
_PROBE_DEADLINE_SECONDS = 4 * _REQUEST_TIMEOUT_SECONDS
# Hard ceiling for the whole probe loop. After this elapses, any probe still
# running is marked as a transient warning so the test never hangs.
_GLOBAL_DEADLINE_SECONDS = 30 * 60
# Emit a "[done/total] elapsed=Ns" line every N completions.
_PROGRESS_INTERVAL = 25
_SUPPRESSION_RULE = "docker-reachable"
_USER_AGENT = "infinito-nexus-image-reachability"

# Map source-registry host (as recorded by iter_role_images.registry) to the
# host that actually serves the Docker Registry v2 API. docker.io and its
# aliases all route to registry-1.docker.io; the rest serve their own.
_REGISTRY_API_HOST = {
    "docker.io": "registry-1.docker.io",
    "registry-1.docker.io": "registry-1.docker.io",
    "index.docker.io": "registry-1.docker.io",
    "ghcr.io": "ghcr.io",
    "quay.io": "quay.io",
    "mcr.microsoft.com": "mcr.microsoft.com",
}

_MANIFEST_ACCEPT = (
    "application/vnd.docker.distribution.manifest.v2+json, "
    "application/vnd.docker.distribution.manifest.list.v2+json, "
    "application/vnd.oci.image.manifest.v1+json, "
    "application/vnd.oci.image.index.v1+json"
)

# WWW-Authenticate Bearer params look like:  Bearer realm="...",service="...",scope="..."
_BEARER_PARAM_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')


@dataclass(frozen=True)
class _Probe:
    role: str
    service: str
    source: str  # e.g. docker.io/library/postgres:16
    config_path: Path


@dataclass(frozen=True)
class _Result:
    probe: _Probe
    ok: bool
    fatal: bool
    detail: str


def _split_source(source: str) -> tuple[str, str, str] | None:
    """Split ``<registry>/<name>:<tag>`` → ``(api_host, name, tag)``.

    Returns ``None`` for sources we cannot route (unknown registry, digest
    ref, missing tag). Such pins fall back to a warning at probe time.
    """
    registry, sep, rest = source.partition("/")
    if not sep or not rest:
        return None
    api_host = _REGISTRY_API_HOST.get(registry)
    if not api_host:
        return None
    if "@sha256:" in rest:
        return None
    name, sep, tag = rest.rpartition(":")
    if not sep or "/" in tag:
        return None
    return api_host, name, tag


def _request_token(realm: str, service: str | None, scope: str | None) -> str | None:
    params: dict[str, str] = {}
    if service:
        params["service"] = service
    if scope:
        params["scope"] = scope
    try:
        resp = requests.get(
            realm,
            params=params,
            headers={"User-Agent": _USER_AGENT},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    try:
        body = resp.json()
    except ValueError:
        return None
    return body.get("token") or body.get("access_token")


def _head_manifest(
    api_host: str, name: str, tag: str, token: str | None
) -> tuple[int, str]:
    url = f"https://{api_host}/v2/{name}/manifests/{tag}"
    headers = {"Accept": _MANIFEST_ACCEPT, "User-Agent": _USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.head(
            url,
            headers=headers,
            allow_redirects=True,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        return -1, type(exc).__name__
    return resp.status_code, resp.reason or ""


def _probe_http(api_host: str, name: str, tag: str) -> tuple[int, str]:
    status, reason = _head_manifest(api_host, name, tag, token=None)
    if status != 401:
        return status, reason

    # 401 → negotiate a bearer token from WWW-Authenticate and retry once.
    try:
        challenge = requests.head(
            f"https://{api_host}/v2/{name}/manifests/{tag}",
            headers={"User-Agent": _USER_AGENT},
            allow_redirects=True,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        return -1, type(exc).__name__

    www_auth = challenge.headers.get("WWW-Authenticate", "")
    if not www_auth.lower().startswith("bearer "):
        return 401, "no Bearer challenge"

    params = dict(_BEARER_PARAM_RE.findall(www_auth))
    realm = params.get("realm")
    if not realm:
        return 401, "Bearer challenge without realm"

    token = _request_token(realm, params.get("service"), params.get("scope"))
    if not token:
        return 401, "token fetch failed"

    return _head_manifest(api_host, name, tag, token=token)


def _classify(status: int, reason: str) -> tuple[bool, bool, str]:
    if 200 <= status < 300:
        return True, False, ""
    if status == 404:
        return False, True, "manifest not found (404)"
    if status == -1:
        return False, False, f"network error: {reason}"
    return False, False, f"HTTP {status} {reason}".strip()


def _inspect(probe: _Probe) -> _Result:
    parts = _split_source(probe.source)
    if parts is None:
        return _Result(probe, False, False, f"unroutable source: {probe.source}")
    start = time.monotonic()
    status, reason = _probe_http(*parts)
    if time.monotonic() - start > _PROBE_DEADLINE_SECONDS:
        return _Result(
            probe, False, False, f"probe budget exceeded ({_PROBE_DEADLINE_SECONDS}s)"
        )
    ok, fatal, detail = _classify(status, reason)
    return _Result(probe, ok, fatal, detail)


def _collect_probes(repo_root: Path) -> list[_Probe]:
    roles_root = repo_root / "roles"
    suppressed_by_role: dict[Path, set[str]] = {}

    probes: list[_Probe] = []
    for ref in iter_role_images(repo_root):
        if ref.source_file != ROLE_FILE_META_SERVICES:
            continue
        config_path = roles_root / ref.role / ROLE_FILE_META_SERVICES

        if config_path not in suppressed_by_role:
            suppressed_by_role[config_path] = suppressed_services(
                config_path, rule=_SUPPRESSION_RULE
            )

        if ref.service in suppressed_by_role[config_path]:
            continue

        probes.append(
            _Probe(
                role=ref.role,
                service=ref.service,
                source=ref.source,
                config_path=config_path,
            )
        )
    return probes


class TestDockerImageReachable(unittest.TestCase):
    """Fail when an image pin in services.yml does not resolve upstream."""

    def test_image_pins_resolve(self) -> None:
        probes = _collect_probes(_REPO_ROOT)
        self.assertTrue(probes, "No image pins found")
        total = len(probes)

        results: list[_Result] = []
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_WORKERS)
        future_to_probe = {executor.submit(_inspect, p): p for p in probes}
        completed = 0
        start = time.monotonic()
        try:
            for future in concurrent.futures.as_completed(
                future_to_probe, timeout=_GLOBAL_DEADLINE_SECONDS
            ):
                results.append(future.result())
                completed += 1
                if completed % _PROGRESS_INTERVAL == 0 or completed == total:
                    elapsed = time.monotonic() - start
                    print(
                        f"  [{completed}/{total}] elapsed={elapsed:.1f}s",
                        file=sys.stderr,
                        flush=True,
                    )
        except concurrent.futures.TimeoutError:
            elapsed = time.monotonic() - start
            unfinished = [p for f, p in future_to_probe.items() if not f.done()]
            results.extend(
                _Result(
                    probe,
                    False,
                    False,
                    f"global deadline {_GLOBAL_DEADLINE_SECONDS}s exceeded",
                )
                for probe in unfinished
            )
            print(
                f"  global deadline reached at {elapsed:.1f}s; "
                f"{len(unfinished)} probes still running "
                f"(marked as warn, not waited for)",
                file=sys.stderr,
                flush=True,
            )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        failures = [r for r in results if not r.ok and r.fatal]
        warnings_list = [r for r in results if not r.ok and not r.fatal]

        for r in warnings_list:
            warning(
                f"{r.probe.role}/{r.probe.service}: cannot verify "
                f"{r.probe.source} ({r.detail})",
                title="Unreachable Docker image (transient)",
                file=str(r.probe.config_path.relative_to(_REPO_ROOT)),
            )

        for r in failures:
            error(
                f"{r.probe.role}/{r.probe.service}: {r.probe.source} "
                f"does not exist upstream ({r.detail})",
                title="Broken Docker image pin",
                file=str(r.probe.config_path.relative_to(_REPO_ROOT)),
            )

        if failures:
            joined = "\n".join(
                f"  - {r.probe.role}/{r.probe.service}: {r.probe.source} ({r.detail})"
                for r in failures
            )
            self.fail(
                f"{len(failures)} image pin(s) do not resolve upstream:\n{joined}\n"
                f"\n💡 Pin a real tag, or suppress with `# nocheck: {_SUPPRESSION_RULE}` "
                f"above the `version:` key."
            )


if __name__ == "__main__":
    unittest.main()
