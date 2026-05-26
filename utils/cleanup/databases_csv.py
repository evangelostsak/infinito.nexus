"""databases.csv stale-row cleanup helper.

``svc-bkp-container-2-local`` seeds per-consumer rows into
``/var/lib/infinito/secrets/databases.csv`` via ``baudolo-seed`` from
``roles/svc-bkp-container-2-local/tasks/04_seed-database-to-backup.yml``.
The format written by ``baudolo-seed`` (verified against
``baudolo.seed.__main__:check_and_add_entry``) is a **semicolon-
separated** CSV with a header row and these columns::

    instance;database;username;password

The matrix-deploy variant transition wipes the consumer's compose stack
(and the named DB volume via ``compose down -v`` in
``scripts/container/purge/entity/compose.sh``) but the CSV survives. When
the next round does not redeploy the consumer, its row stays behind with
the now-invalid password, and ``baudolo`` fails the dump against a
freshly initialised RDBMS user that does not exist (job 77797356000 on
run 26428080957: matomo dump → ``Access denied (1045)``).

This module strips rows whose ``database`` or ``username`` column
matches the consumer entity derived from the supplied application ids,
following the same shape as ``utils.cleanup.tokens``. It is invoked by
``scripts/container/purge/apps.sh`` alongside the token-store wipe.
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

from utils.roles.entity_name import get_entity_name

DEFAULT_CSV = Path("/var/lib/infinito/secrets/databases.csv")

# baudolo-seed always writes ';' (see baudolo.seed.__main__: `df.to_csv(..., sep=";")`).
_CSV_DELIMITER = ";"
_HEADER_COLUMNS = ("instance", "database", "username", "password")


def _resolve_csv_file() -> Path:
    env_path = os.environ.get("FILE_DATABASE_SECRETS")
    return Path(env_path) if env_path else DEFAULT_CSV


def _row_matches(row: list[str], targets: set[str]) -> bool:
    if len(row) < 3:
        return False
    database = row[1].strip()
    username = row[2].strip()
    return database in targets or username in targets


def _is_header(row: list[str]) -> bool:
    if len(row) < len(_HEADER_COLUMNS):
        return False
    return all(
        row[i].strip().lower() == _HEADER_COLUMNS[i]
        for i in range(len(_HEADER_COLUMNS))
    )


def wipe_database_entries(
    app_ids: list[str], csv_file: Path | None = None
) -> list[str]:
    """Remove rows owned by *app_ids* from the central databases CSV.

    Matches rows where either the ``database`` column (index 1) or the
    ``username`` column (index 2) equals an entity name derived from one
    of *app_ids* via ``utils.roles.entity_name.get_entity_name``. The
    CSV is rewritten only when at least one row was removed; the header
    row and blank lines are preserved verbatim.

    Returns the list of removed identifiers (``<database>:<username>``)
    for observability.
    """
    path = csv_file or _resolve_csv_file()
    if not path.exists():
        return []

    targets: set[str] = set()
    for app_id in app_ids:
        entity = get_entity_name(app_id)
        if entity:
            targets.add(entity)
    if not targets:
        return []

    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh, delimiter=_CSV_DELIMITER))

    kept: list[list[str]] = []
    removed: list[str] = []
    for row in rows:
        if not row:
            kept.append(row)
            continue
        if _is_header(row):
            kept.append(row)
            continue
        if _row_matches(row, targets):
            removed.append(f"{row[1].strip()}:{row[2].strip()}")
            continue
        kept.append(row)

    if removed:
        with path.open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh, delimiter=_CSV_DELIMITER).writerows(kept)

    return removed


def main(argv: list[str]) -> int:
    if not argv:
        print(
            "usage: python -m utils.cleanup.databases_csv <APP_ID> [APP_ID ...]",
            file=sys.stderr,
        )
        return 2

    removed = wipe_database_entries(argv)
    if removed:
        print(f">>> Wiped databases.csv entries: {', '.join(removed)}")
    else:
        print(">>> No databases.csv entries to wipe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
