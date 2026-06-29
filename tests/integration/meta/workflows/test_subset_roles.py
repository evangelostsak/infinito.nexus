import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import PROJECT_ROOT

SCRIPT_REL = Path("scripts/meta/resolve/pr/subset_roles.py")
SCRIPT_PATH = PROJECT_ROOT / SCRIPT_REL


class TestSubsetRoles(unittest.TestCase):
    """Exercises the '🧩 Subset' resolver.

    The "no subset label" case (existing diff behaviour stays unchanged) is
    covered by test_diff_affected_roles.py: this script only ever runs when
    the label gates it in entry-pull-request-change.yml.
    """

    def _run(self, *, body: str, roles: tuple[str, ...] = ("web-app-foo",)):
        tmp = Path(tempfile.mkdtemp(prefix="subset-roles-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)

        # Plant the real script at its expected relative path so REPO_ROOT
        # (parents[4]) lands inside the temp tree, and create the roles/ dirs
        # the validation checks against.
        script_target = tmp / SCRIPT_REL
        script_target.parent.mkdir(parents=True)
        shutil.copy2(SCRIPT_PATH, script_target)
        for role in roles:
            (tmp / "roles" / role).mkdir(parents=True)

        output_file = tmp / "output.txt"
        output_file.touch()

        env = os.environ.copy()
        env["PR_BODY"] = body
        env["GITHUB_OUTPUT"] = str(output_file)

        result = subprocess.run(
            ["python", str(script_target)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        outputs = {}
        for line in output_file.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                outputs[key] = value
        return result, outputs

    def test_valid_roles_produce_whitelist(self):
        body = "## Roles\n\n```yaml\nroles:\n  - web-app-foo\n  - web-app-bar\n```\n"
        result, outputs = self._run(body=body, roles=("web-app-foo", "web-app-bar"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(outputs["whitelist"], "web-app-foo web-app-bar")
        self.assertEqual(outputs["roles_only"], "true")

    def test_invalid_yaml_fails(self):
        body = "```yaml\nroles:\n  - web-app-foo\n   bad: : :\n```\n"
        result, outputs = self._run(body=body)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid YAML", result.stderr)
        self.assertNotIn("whitelist", outputs)

    def test_unknown_role_fails(self):
        body = "```yaml\nroles:\n  - web-app-foo\n  - web-app-ghost\n```\n"
        result, outputs = self._run(body=body, roles=("web-app-foo",))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("web-app-ghost", result.stderr)
        self.assertNotIn("whitelist", outputs)

    def test_path_traversal_id_is_rejected(self):
        body = "```yaml\nroles:\n  - ../../etc\n```\n"
        result, outputs = self._run(body=body)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid role id", result.stderr)
        self.assertNotIn("whitelist", outputs)

    def test_empty_role_list_fails(self):
        body = "```yaml\nroles:\n```\n"
        result, _ = self._run(body=body)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("empty", result.stderr)

    def test_missing_block_fails(self):
        result, _ = self._run(body="No machine-readable roles block here.\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no fenced", result.stderr)


if __name__ == "__main__":
    unittest.main()
