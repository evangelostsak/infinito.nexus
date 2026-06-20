from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from cli.meta.roles.applications.ressources import __main__ as cli


class TestCliMain(unittest.TestCase):
    def test_text_format_runs_end_to_end(self) -> None:
        fake_apps = {
            "web-app-x": {
                "services": {
                    "x": {
                        "cpus": 1,
                        "mem_reservation": "100m",
                        "mem_limit": "200m",
                        "pids_limit": 64,
                    }
                }
            }
        }

        with (
            patch.object(
                cli, "load_applications_from_roles_dir", return_value=fake_apps
            ),
            patch.object(
                cli, "build_service_registry_from_applications", return_value={}
            ),
            patch.object(cli.sys, "argv", ["prog", "--role", "web-app-x"]),
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.main()

        self.assertEqual(rc, 0)
        output = out.getvalue()
        self.assertIn("web-app-x", output)
        self.assertIn("TOTAL", output)

    def test_json_format_runs_end_to_end(self) -> None:
        fake_apps = {
            "web-app-x": {
                "services": {
                    "x": {
                        "cpus": 2,
                        "mem_reservation": "1g",
                        "mem_limit": "2g",
                        "pids_limit": 128,
                    }
                }
            }
        }

        with (
            patch.object(
                cli, "load_applications_from_roles_dir", return_value=fake_apps
            ),
            patch.object(
                cli, "build_service_registry_from_applications", return_value={}
            ),
            patch.object(
                cli.sys,
                "argv",
                ["prog", "--role", "web-app-x", "--format", "json"],
            ),
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.main()

        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["role"], "web-app-x")
        self.assertEqual(payload["totals"]["mem_limit"]["bytes"], 2_000_000_000)
        self.assertEqual(payload["totals"]["cpus"]["value"], 2.0)


if __name__ == "__main__":
    unittest.main()
