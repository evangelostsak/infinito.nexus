"""Unit tests for `utils.cleanup.databases_csv` (databases.csv wipe helper)."""

from __future__ import annotations

import csv
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.cleanup.databases_csv import main, wipe_database_entries

# Mirror the baudolo-seed format exactly: ';' separator, header row, four
# columns in order instance/database/username/password.
_HEADER = "instance;database;username;password\n"


class DatabasesCsvTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.csv_file = Path(self._tmp.name) / "databases.csv"

    def _write(self, content: str) -> None:
        self.csv_file.write_text(content, encoding="utf-8")

    def _read(self) -> list[list[str]]:
        with self.csv_file.open(newline="", encoding="utf-8") as fh:
            return list(csv.reader(fh, delimiter=";"))


class TestWipeDatabaseEntries(DatabasesCsvTestBase, unittest.TestCase):
    def test_removes_matching_row_by_name(self):
        self._write(
            _HEADER
            + "mariadb;matomo;matomo;pw1\n"
            + "postgres;keycloak;keycloak;pw2\n"
            + "mariadb;nextcloud;nextcloud;pw3\n"
        )

        removed = wipe_database_entries(["web-app-matomo"], csv_file=self.csv_file)

        self.assertEqual(removed, ["matomo:matomo"])
        self.assertEqual(
            self._read(),
            [
                ["instance", "database", "username", "password"],
                ["postgres", "keycloak", "keycloak", "pw2"],
                ["mariadb", "nextcloud", "nextcloud", "pw3"],
            ],
        )

    def test_no_match_does_not_rewrite_file(self):
        self._write(_HEADER + "postgres;keycloak;keycloak;pw2\n")
        before_mtime = self.csv_file.stat().st_mtime_ns

        removed = wipe_database_entries(["web-app-matomo"], csv_file=self.csv_file)

        self.assertEqual(removed, [])
        self.assertEqual(self.csv_file.stat().st_mtime_ns, before_mtime)

    def test_missing_file_returns_empty(self):
        removed = wipe_database_entries(["web-app-matomo"], csv_file=self.csv_file)

        self.assertEqual(removed, [])
        self.assertFalse(self.csv_file.exists())

    def test_multiple_app_ids_in_one_call(self):
        self._write(
            _HEADER
            + "mariadb;matomo;matomo;pw1\n"
            + "postgres;keycloak;keycloak;pw2\n"
            + "mariadb;nextcloud;nextcloud;pw3\n"
        )

        removed = wipe_database_entries(
            ["web-app-matomo", "web-app-keycloak"],
            csv_file=self.csv_file,
        )

        self.assertEqual(sorted(removed), ["keycloak:keycloak", "matomo:matomo"])
        self.assertEqual(
            self._read(),
            [
                ["instance", "database", "username", "password"],
                ["mariadb", "nextcloud", "nextcloud", "pw3"],
            ],
        )

    def test_username_match_when_database_is_wildcard(self):
        # baudolo-seed encodes "dump all databases" as the literal '*' in
        # the database column; the consumer's entity still matches via
        # the username column.
        self._write(_HEADER + "mariadb;*;matomo;pw1\npostgres;*;keycloak;pw2\n")

        removed = wipe_database_entries(["web-app-matomo"], csv_file=self.csv_file)

        self.assertEqual(removed, ["*:matomo"])
        self.assertEqual(
            self._read(),
            [
                ["instance", "database", "username", "password"],
                ["postgres", "*", "keycloak", "pw2"],
            ],
        )

    def test_unknown_app_id_no_op(self):
        self._write(_HEADER + "mariadb;matomo;matomo;pw1\n")

        removed = wipe_database_entries(
            ["web-app-does-not-exist"], csv_file=self.csv_file
        )

        # get_entity_name falls back to role_name when no category match;
        # 'web-app-does-not-exist' does not collide with 'matomo' → no op.
        self.assertEqual(removed, [])

    def test_blank_lines_are_preserved(self):
        self._write(
            _HEADER
            + "mariadb;matomo;matomo;pw1\n"
            + "\n"
            + "postgres;keycloak;keycloak;pw2\n"
        )

        removed = wipe_database_entries(["web-app-matomo"], csv_file=self.csv_file)

        self.assertEqual(removed, ["matomo:matomo"])
        self.assertEqual(
            self._read(),
            [
                ["instance", "database", "username", "password"],
                [],
                ["postgres", "keycloak", "keycloak", "pw2"],
            ],
        )

    def test_header_is_kept_even_when_all_data_rows_removed(self):
        self._write(_HEADER + "mariadb;matomo;matomo;pw1\n")

        removed = wipe_database_entries(["web-app-matomo"], csv_file=self.csv_file)

        self.assertEqual(removed, ["matomo:matomo"])
        self.assertEqual(
            self._read(),
            [["instance", "database", "username", "password"]],
        )

    def test_short_row_is_kept(self):
        # Defensive: malformed row with < 3 columns should not be removed
        # (no database/username to match against).
        self._write(_HEADER + "garbage\nmariadb;matomo;matomo;pw1\n")

        removed = wipe_database_entries(["web-app-matomo"], csv_file=self.csv_file)

        self.assertEqual(removed, ["matomo:matomo"])
        self.assertEqual(
            self._read(),
            [
                ["instance", "database", "username", "password"],
                ["garbage"],
            ],
        )

    def test_csv_without_header_is_still_processed(self):
        # Defensive: in case `databases.csv` was created without the
        # baudolo header (e.g. legacy file produced before the pandas
        # rewrite), rows that match should still be removed.
        self._write("mariadb;matomo;matomo;pw1\npostgres;keycloak;keycloak;pw2\n")

        removed = wipe_database_entries(["web-app-matomo"], csv_file=self.csv_file)

        self.assertEqual(removed, ["matomo:matomo"])
        self.assertEqual(
            self._read(),
            [["postgres", "keycloak", "keycloak", "pw2"]],
        )


class TestMainShim(DatabasesCsvTestBase, unittest.TestCase):
    def test_no_argv_prints_usage_and_returns_2(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            rc = main([])
        self.assertEqual(rc, 2)
        self.assertIn("usage:", stderr.getvalue())

    def test_main_uses_default_path_when_no_override(self):
        # With no FILE_DATABASE_SECRETS env var and the default path
        # missing on the test host, main MUST still return 0 and report
        # a no-op.
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            rc = main(["web-app-nonexistent"])
        self.assertEqual(rc, 0)
        self.assertIn("No databases.csv entries to wipe", stdout.getvalue())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
