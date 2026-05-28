"""Guard: every role with ``services.sso.flavor: oauth2`` AND ``sso.enabled``
potentially truthy in ``meta/services.yml`` MUST allocate an SSO-proxy
listen port via ``<service>.ports.local.sso: <port>`` in the same file.

Background
==========
When a role's SSO flavor is oauth2 (i.e. the oauth2-proxy sidecar fronts
the upstream), the proxy needs a unique local port to listen on. The
port is declared under one of the role's service entries'
``ports.local.sso`` key (typically the role's primary service block).
Without this, the proxy renders without a port and rollout silently
produces a half-wired vhost.

This is the renamed in-tree successor of the legacy oauth2/oidc-split
proxy-ports guard; the contract ("oauth2-flavored SSO roles MUST
allocate an SSO-proxy port") is unchanged.
"""

from __future__ import annotations

import unittest

from utils.cache.yaml import load_yaml
from utils.roles.applications.services.sso import is_potentially_enabled
from utils.roles.mapping import ROLE_FILE_META_SERVICES

from . import PROJECT_ROOT

ROLES_DIR = PROJECT_ROOT / "roles"


def _has_sso_port(services: dict) -> bool:
    """Return True iff any service entry declares ``ports.local.sso``."""
    for value in services.values():
        if not isinstance(value, dict):
            continue
        ports = value.get("ports")
        if not isinstance(ports, dict):
            continue
        local = ports.get("local")
        if not isinstance(local, dict):
            continue
        if local.get("sso") is not None:
            return True
    return False


class TestSsoProxyPorts(unittest.TestCase):
    def test_oauth2_flavor_role_has_proxy_port(self) -> None:
        failures: list[str] = []
        for role_path in sorted(ROLES_DIR.iterdir()):
            if not role_path.is_dir():
                continue
            services_file = role_path / ROLE_FILE_META_SERVICES
            if not services_file.exists():
                continue

            try:
                services = load_yaml(services_file, default_if_missing={})
            except (ValueError, OSError) as error:
                failures.append(
                    f"{role_path.name}: failed to load meta/services.yml ({error})"
                )
                continue

            sso = services.get("sso") if isinstance(services, dict) else None
            if not isinstance(sso, dict):
                continue
            if sso.get("flavor") != "oauth2":
                continue
            if not is_potentially_enabled(sso.get("enabled")):
                continue

            if not _has_sso_port(services):
                failures.append(
                    f"{role_path.name}: services.sso.flavor=oauth2 with "
                    f"enabled potentially truthy but no service declares "
                    f"ports.local.sso. Add `sso: <port>` under the primary "
                    f"service's `ports.local:` block in meta/services.yml."
                )

        if failures:
            self.fail(
                "Roles with sso.flavor=oauth2 must allocate an SSO-proxy port:\n"
                + "\n".join(f"  - {entry}" for entry in failures)
            )


if __name__ == "__main__":
    unittest.main()
