"""Guards for the per-deploy credential rotation path of web-app-openbao.

The platform regenerates generated-algorithm credentials on every deploy, so the
seal key and AppRole a run is handed differ from the ones the running instance
was configured with. Three things carry that transition, and each fails silently
rather than loudly when broken -- a sealed node and an unusable AppRole look
identical to ordinary drift. These tests pin them.
"""

from __future__ import annotations

import unittest

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from utils.cache.files import read_text
from utils.cache.yaml import load_yaml_any

from . import PROJECT_ROOT

ROLE_DIR = PROJECT_ROOT / "roles/web-app-openbao"
TASKS_DIR = ROLE_DIR / "tasks"

HCL_CONTEXT = {
    "OPENBAO_LOG_LEVEL": "info",
    "OPENBAO_DATA_DOCKER": "/openbao/file",
    "OPENBAO_NAME": "openbao",
    "container_port": "8200",
    "OPENBAO_SEAL_KEY_ID": "0123456789abcdef",
    "OPENBAO_SEAL_KEY_PREVIOUS_ID": "fedcba9876543210",
    "OPENBAO_BASE_URL": "https://bao.example.com",
}

ENV_CONTEXT = {
    "OPENBAO_SEAL_KEY": "current-key",
    "OPENBAO_SEAL_KEY_PREVIOUS": "previous-key",
    "container_port": "8200",
}


def jinja_env(searchpath) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(searchpath)),
        undefined=StrictUndefined,
        autoescape=False,  # noqa: S701 - renders HCL and dotenv, not markup
    )
    env.filters["bool"] = bool
    env.filters["dotenv_quote"] = lambda value: f'"{value}"'
    return env


def tasks_of(name: str) -> list[dict]:
    return load_yaml_any(str(TASKS_DIR / name))


class TestSealStanzaRotation(unittest.TestCase):
    def _render(self, rotating: bool) -> str:
        env = jinja_env(ROLE_DIR / "templates")
        return env.get_template("openbao.hcl.j2").render(
            OPENBAO_SEAL_ROTATING=rotating, **HCL_CONTEXT
        )

    def test_the_previous_key_is_offered_while_the_keys_differ(self):
        rendered = self._render(True)
        self.assertIn('previous_key_id = "fedcba9876543210"', rendered)
        self.assertIn('previous_key    = "env://OPENBAO_SEAL_KEY_PREVIOUS"', rendered)

    def test_no_previous_key_is_offered_on_a_first_deploy(self):
        rendered = self._render(False)
        self.assertNotIn("previous_key", rendered)
        self.assertIn('current_key_id = "0123456789abcdef"', rendered)


class TestEnvCarriesThePreviousKey(unittest.TestCase):
    """The shared sys-svc-container include needs a live Ansible context.

    Only the role's own lines are rendered here; the include is dropped, which
    leaves the conditional under test intact.
    """

    def _render(self, rotating: bool) -> str:
        source = read_text(str(ROLE_DIR / "templates/env.j2"))
        body = "\n".join(
            line for line in source.splitlines() if "{% include" not in line
        )
        env = jinja_env(ROLE_DIR / "templates")
        return env.from_string(body).render(
            OPENBAO_SEAL_ROTATING=rotating, **ENV_CONTEXT
        )

    def test_the_previous_key_reaches_the_container_while_rotating(self):
        rendered = self._render(True)
        self.assertIn('OPENBAO_SEAL_KEY_PREVIOUS="previous-key"', rendered)
        self.assertIn('OPENBAO_SEAL_KEY="current-key"', rendered)

    def test_no_previous_key_is_exported_on_a_first_deploy(self):
        rendered = self._render(False)
        self.assertNotIn("OPENBAO_SEAL_KEY_PREVIOUS", rendered)
        self.assertIn('OPENBAO_SEAL_KEY="current-key"', rendered)


class TestAppliedStateIsReadBeforeTheConfigIsRendered(unittest.TestCase):
    def test_the_state_read_precedes_the_backend_include(self):
        """env.j2 is rendered by sys-stk-backend.

        Reading the applied state after that include leaves the container
        without the previous seal key, and the node comes up sealed with no way
        to decrypt its own store.
        """
        tasks = tasks_of("00_core.yml")
        state_read = next(
            i
            for i, task in enumerate(tasks)
            if task.get("ansible.builtin.slurp", {})
            .get("src", "")
            .endswith("OPENBAO_APPLIED_STATE_HOST }}")
        )
        backend = next(
            i
            for i, task in enumerate(tasks)
            if task.get("include_role", {}).get("name") == "sys-stk-backend"
        )
        self.assertLess(state_read, backend)


class TestAppRoleLoginToleratesRotation(unittest.TestCase):
    def setUp(self):
        self.tasks = tasks_of("01_init.yml")

    def test_the_inventory_login_does_not_abort_the_play(self):
        login = next(
            task
            for task in self.tasks
            if task.get("register") == "openbao_approle_login"
        )
        self.assertIs(login.get("failed_when"), False)

    def test_a_fallback_login_uses_the_previously_applied_credentials(self):
        fallback = next(
            task
            for task in self.tasks
            if task.get("register") == "openbao_approle_login_previous"
        )
        self.assertIs(
            fallback.get("failed_when"),
            False,
            "a failing fallback must reach the guard, not abort with a raw 403",
        )
        self.assertIn(
            "OPENBAO_APPLIED.approle_role_id",
            fallback["ansible.builtin.shell"],
        )
        self.assertIn(
            "OPENBAO_APPLIED.approle_secret_id",
            fallback["args"]["stdin"],
        )

    def test_the_stored_token_is_whichever_login_succeeded(self):
        """A regression here re-introduces the bug this path exists to fix.

        Storing openbao_approle_login.stdout feeds the token helper an empty
        string on every rotated deploy, and reconciliation then fails on the
        first write instead of on the login.
        """
        store = next(
            task
            for task in self.tasks
            if "bao login -no-print" in str(task.get("ansible.builtin.shell", ""))
        )
        self.assertIn("openbao_approle_token", store["args"]["stdin"])

    def test_neither_credential_being_accepted_fails_loudly(self):
        self.assertTrue(
            any("ansible.builtin.fail" in task for task in self.tasks),
            "a rotated-out instance must fail with a message, not a bare 403",
        )

    def test_the_rotation_pass_runs_before_the_token_is_dropped(self):
        rotate = next(
            i
            for i, task in enumerate(self.tasks)
            if task.get("ansible.builtin.include_tasks", {}) == "06_rotate.yml"
        )
        drop = next(
            i
            for i, task in enumerate(self.tasks)
            if "token revoke -self" in str(task.get("ansible.builtin.shell", ""))
        )
        self.assertLess(rotate, drop)


class TestTheSecretIdSwapIsGuarded(unittest.TestCase):
    """Re-registering an unchanged SecretID answers 500, and the old one must go.

    `custom-secret-id` is not idempotent: writing a SecretID the role already
    holds fails with `SecretID is already registered`, so an unguarded re-pin
    breaks every deploy that did not rotate. Leaving the previous SecretID
    registered is the opposite failure -- the rotation would revoke nothing.
    """

    def setUp(self):
        self.tasks = tasks_of("06_rotate.yml")

    def _guarded(self, fragment: str) -> dict:
        return next(
            task
            for task in self.tasks
            if fragment in str(task.get("ansible.builtin.shell", ""))
        )

    def test_the_new_secret_id_is_registered_only_while_rotating(self):
        task = self._guarded("custom-secret-id")
        self.assertEqual(task["when"], "OPENBAO_SECRET_ID_ROTATING | bool")
        self.assertIn("OPENBAO_APPROLE_SECRET_ID", task["args"]["stdin"])

    def test_the_previous_secret_id_is_destroyed_while_rotating(self):
        task = self._guarded("secret-id/destroy")
        self.assertEqual(task["when"], "OPENBAO_SECRET_ID_ROTATING | bool")
        self.assertIn("OPENBAO_SECRET_ID_REGISTERED", task["args"]["stdin"])

    def test_the_role_id_is_re_pinned_unconditionally(self):
        task = self._guarded("role-id")
        self.assertNotIn("when", task)


class TestTheRegisteredSecretIdComesFromTheLogin(unittest.TestCase):
    def test_it_is_the_credential_that_was_just_accepted(self):
        """Deriving it from the state file instead would be wrong.

        On a deploy whose inventory credentials still work, the state file may
        hold an older value; destroying that would leave the live SecretID
        registered and revoke nothing.
        """
        tasks = tasks_of("01_init.yml")
        keep = next(
            task
            for task in tasks
            if "openbao_secret_id_registered"
            in task.get("ansible.builtin.set_fact", {})
        )
        expression = keep["ansible.builtin.set_fact"]["openbao_secret_id_registered"]
        self.assertIn("openbao_approle_login.rc == 0", expression)
        self.assertIn("OPENBAO_APPROLE_SECRET_ID", expression)
        self.assertIn("OPENBAO_APPLIED.approle_secret_id", expression)


class TestTheAppliedStateIsRecorded(unittest.TestCase):
    def test_every_credential_the_next_deploy_needs_is_written(self):
        tasks = tasks_of("06_rotate.yml")
        record = next(task for task in tasks if "ansible.builtin.copy" in task)
        applied = record["vars"]["openbao_applied_now"]
        self.assertEqual(
            sorted(applied),
            ["approle_role_id", "approle_secret_id", "seal_key"],
        )
        self.assertEqual(record["ansible.builtin.copy"]["mode"], "0600")
        self.assertEqual(record["ansible.builtin.copy"]["owner"], "root")

    def test_the_record_is_the_last_thing_the_rotation_does(self):
        """Recording before the pins would claim credentials that never applied."""
        tasks = tasks_of("06_rotate.yml")
        record = next(
            i for i, task in enumerate(tasks) if "ansible.builtin.copy" in task
        )
        self.assertEqual(record, len(tasks) - 1)
