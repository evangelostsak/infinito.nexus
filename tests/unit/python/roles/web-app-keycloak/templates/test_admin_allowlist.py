from __future__ import annotations

import importlib.util
import re
import unittest

from ansible.errors import AnsibleFilterError
from jinja2 import (
    ChoiceLoader,
    DictLoader,
    Environment,
    FileSystemLoader,
    StrictUndefined,
    select_autoescape,
)

from utils.cache.files import iter_project_files_with_content, read_text
from utils.cache.yaml import load_yaml
from utils.networks.proxy import render_proxy_pass
from utils.roles.mapping import ROLE_FILE_META_SERVICES

from . import PROJECT_ROOT

ROLE_DIR = PROJECT_ROOT / "roles/web-app-keycloak"
TEMPLATE = "roles/web-app-keycloak/templates/nginx/admin_allowlist.conf.j2"
CONFIG_PATH = "services.keycloak.admin.allowed_networks"
LOCAL_HTTP_PORT = 8032
NETWORKS = ("203.0.113.0/24", "2001:db8::/48", "198.51.100.7")

STUBBED_INCLUDES = {
    "roles/web-app-keycloak/templates/sso_proxy/following_directives.conf.j2": "SSO_GATE\n",
    "roles/sys-svc-proxy/templates/headers/content_security_policy.conf.j2": "",
    "roles/sys-svc-proxy/templates/headers/access_control_allow.conf.j2": "",
    "roles/sys-svc-proxy/templates/headers/forwarded.conf.j2": "",
    "roles/sys-svc-proxy/templates/headers/untrusted_identity_strips.conf.j2": "",
    "roles/sys-front-inj-all/templates/location.lua.j2": "",
}


def role_filters() -> dict:
    spec = importlib.util.spec_from_file_location(
        "keycloak_admin_networks", ROLE_DIR / "filter_plugins/admin_networks.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FilterModule().filters()


def render(networks, deployment_mode: str = "compose") -> str:
    """Render the allowlist fragment the Keycloak vhost carries.

    Args:
        networks: the value under `services.keycloak.admin.allowed_networks`.
        deployment_mode: the mode `proxy_pass` renders for.
    """
    config = {
        CONFIG_PATH: networks,
        "services.keycloak.ports.local.http": LOCAL_HTTP_PORT,
    }

    def lookup(kind, *args, **kwargs):
        if kind == "config":
            if args[1] in config:
                return config[args[1]]
            return args[2]
        if kind == "proxy_pass":
            return render_proxy_pass(
                f"127.0.0.1:{kwargs['local_port']}",
                deployment_mode,
                tail=kwargs["tail"],
                location=kwargs["location"],
            )
        raise AssertionError(f"unexpected lookup({kind!r}, ...)")

    env = Environment(
        loader=ChoiceLoader(
            [DictLoader(STUBBED_INCLUDES), FileSystemLoader(str(PROJECT_ROOT))]
        ),
        undefined=StrictUndefined,
        autoescape=select_autoescape(),
    )
    env.filters.update(role_filters())
    env.filters["bool"] = lambda value: (
        value
        if isinstance(value, bool)
        else str(value).strip().lower() in {"true", "1", "yes", "on"}
    )
    env.filters["get_entity_name"] = lambda value: value.rsplit("-", 1)[-1]
    return env.get_template(TEMPLATE).render(
        application_id="web-app-keycloak", lookup=lookup
    )


def location_block(rendered: str) -> tuple[str, list[str]]:
    """Return the location's matcher and its directives, one per line.

    Args:
        rendered: the rendered fragment.
    """
    match = re.search(r"location\s+([^{]+?)\s*\{(.*)\}\s*$", rendered, re.DOTALL)
    if match is None:
        raise AssertionError(f"no location block rendered:\n{rendered}")
    directives = [
        line.strip()
        for line in match.group(2).splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return match.group(1).strip(), directives


def covers(matcher: str, path: str) -> bool:
    """Return whether an nginx prefix matcher selects a request path.

    Args:
        matcher: the location matcher, modifier included.
        path: the normalised request path.
    """
    return path.startswith(re.sub(r"^\^~\s*", "", matcher))


class TestShippedValue(unittest.TestCase):
    def test_the_role_ships_no_implicit_allowlist(self):
        services = load_yaml(ROLE_DIR / ROLE_FILE_META_SERVICES)
        self.assertEqual(services["keycloak"]["admin"]["allowed_networks"], [])

    def test_an_empty_list_renders_nothing(self):
        self.assertEqual(render([]).strip(), "")

    def test_the_keycloak_vhost_carries_the_fragment(self):
        self.assertIn(
            "lookup('template', 'nginx/admin_allowlist.conf.j2')",
            read_text(str(ROLE_DIR / "tasks/00_core.yml")),
        )


class TestRestrictedLocation(unittest.TestCase):
    def test_every_network_is_allowed_before_the_rest_is_denied(self):
        _, directives = location_block(render(list(NETWORKS)))
        access = [d for d in directives if d.startswith(("allow ", "deny "))]
        self.assertEqual(
            access,
            [
                "allow 203.0.113.0/24;",
                "allow 2001:db8::/48;",
                "allow 198.51.100.7/32;",
                "deny all;",
            ],
        )

    def test_the_admin_console_and_rest_api_are_covered(self):
        matcher, _ = location_block(render(list(NETWORKS)))
        for path in (
            "/admin",
            "/admin/",
            "/admin/master/console/",
            "/admin/realms/infinito/users",
            "/admin/serverinfo",
        ):
            with self.subTest(path=path):
                self.assertTrue(covers(matcher, path))

    def test_the_oidc_endpoints_stay_public(self):
        matcher, _ = location_block(render(list(NETWORKS)))
        for path in (
            "/",
            "/realms/infinito/protocol/openid-connect/token",
            "/realms/infinito/.well-known/openid-configuration",
            "/realms/infinito/account/",
            "/resources/abc/admin/keycloak.v2/main.js",
        ):
            with self.subTest(path=path):
                self.assertFalse(covers(matcher, path))

    def test_no_regex_location_can_take_an_admin_path_over(self):
        matcher, _ = location_block(render(list(NETWORKS)))
        self.assertTrue(
            matcher.startswith("^~ "),
            f"'{matcher}' lets a regex location win over the allowlist",
        )

    def test_compose_passes_the_request_path_unchanged(self):
        _, directives = location_block(render(list(NETWORKS)))
        self.assertIn(
            f"proxy_pass http://127.0.0.1:{LOCAL_HTTP_PORT}/admin;", directives
        )

    def test_swarm_passes_the_raw_request_uri(self):
        _, directives = location_block(render(list(NETWORKS), "swarm"))
        self.assertIn("proxy_pass http://$proxy_pass_upstream$request_uri;", directives)

    def test_the_location_strips_forged_identity_headers(self):
        rendered = render(list(NETWORKS))
        self.assertIn('proxy_set_header X-Forwarded-User "";', rendered)
        self.assertNotIn("SSO_GATE", rendered)


class TestDeclaredValues(unittest.TestCase):
    def test_spellings_of_one_network_render_one_allow(self):
        _, directives = location_block(
            render(["2001:db8::1", "2001:0db8::1/128", " 2001:db8::1 "])
        )
        self.assertEqual(
            [d for d in directives if d.startswith("allow ")],
            ["allow 2001:db8::1/128;"],
        )

    def test_malformed_values_fail_the_render(self):
        for value in (
            "203.0.113.0/24",
            None,
            ["all"],
            ["203.0.113.7/24"],
            ["auth.example.com"],
            [""],
            [42],
        ):
            with self.subTest(value=value), self.assertRaises(AnsibleFilterError):
                render(value)


class TestDeployAdminCallsBypassTheVhost(unittest.TestCase):
    LOGIN = re.compile(
        r"config credentials[\s\\]*--server\s+(\"[^\"]*\"|\{\{.*?\}\}|\S+)", re.DOTALL
    )
    INTERNAL_URL_DEFINITION = re.compile(
        r"^\s*KEYCLOAK_SERVER_INTERNAL_URL:\s*\"([^\"]+)\"", re.MULTILINE
    )
    LOOPBACK = re.compile(r"^http://(127\.0\.0\.1|localhost|\[::1\]):\d+$")

    def _role_sources(self) -> dict[str, str]:
        return {
            path: text
            for path, text in iter_project_files_with_content(
                extensions=(".yml", ".sh", ".j2"), exclude_tests=True
            )
            if "/roles/" in path
        }

    def test_every_kcadm_login_targets_the_container_loopback(self):
        servers = [
            (name, match.group(1).strip('"'))
            for name, text in self._role_sources().items()
            for match in self.LOGIN.finditer(text)
        ]
        self.assertTrue(servers, "no kcadm login found, the scan is vacuous")
        for name, server in servers:
            with self.subTest(source=name, server=server):
                self.assertTrue(
                    server == "{{ KEYCLOAK_SERVER_INTERNAL_URL }}"
                    or self.LOOPBACK.match(server),
                    f"{name} logs kcadm in through {server}, which crosses the "
                    "public vhost and its admin allowlist",
                )

    def test_the_internal_url_is_loopback_wherever_it_is_defined(self):
        definitions = [
            (name, match.group(1))
            for name, text in self._role_sources().items()
            for match in self.INTERNAL_URL_DEFINITION.finditer(text)
        ]
        self.assertTrue(definitions, "KEYCLOAK_SERVER_INTERNAL_URL is defined nowhere")
        for name, url in definitions:
            with self.subTest(source=name):
                self.assertRegex(url, self.LOOPBACK)


if __name__ == "__main__":
    unittest.main()
