import os
import unittest

import yaml


class TestWebAppPenpotRole(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        cls.role_dir = os.path.join(cls.repo_root, "roles", "web-app-penpot")

    def test_role_directory_exists(self):
        self.assertTrue(os.path.isdir(self.role_dir), "roles/web-app-penpot must exist")

    def test_required_role_files_exist(self):
        required = [
            "README.md",
            "config/main.yml",
            "meta/main.yml",
            "schema/main.yml",
            "tasks/main.yml",
            "templates/compose.yml.j2",
            "templates/env.j2",
            "templates/playwright.env.j2",
            "files/playwright.spec.js",
            "vars/main.yml",
        ]

        missing = []
        for rel_path in required:
            abs_path = os.path.join(self.role_dir, rel_path)
            if not os.path.isfile(abs_path):
                missing.append(rel_path)

        if missing:
            self.fail(
                "Missing required Penpot role files:\n" + "\n".join(sorted(missing))
            )

    def test_config_declares_service_dependencies(self):
        config_path = os.path.join(self.role_dir, "config", "main.yml")
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        services = ((config.get("compose") or {}).get("services")) or {}

        for service_name in ("penpot", "postgres", "redis", "minio"):
            with self.subTest(service=service_name):
                self.assertIn(service_name, services)

        self.assertTrue(services["postgres"].get("enabled"))
        self.assertTrue(services["redis"].get("enabled"))
        self.assertTrue(services["minio"].get("enabled"))

    def test_schema_declares_secrets(self):
        schema_path = os.path.join(self.role_dir, "schema", "main.yml")
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = yaml.safe_load(f) or {}

        credentials = schema.get("credentials") or {}
        for key in (
            "secret_key",
            "objects_access_key",
            "objects_secret_key",
            "objects_bucket_name",
        ):
            with self.subTest(credential=key):
                self.assertIn(key, credentials)


if __name__ == "__main__":
    unittest.main()
