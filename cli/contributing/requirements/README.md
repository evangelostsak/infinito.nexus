# Requirements

The requirements archive helper that used to live here has moved to
[kpmx](https://pypi.org/project/kpmx/) so every kpmx-managed repository
can rely on the same archival convention.

Run it via:

```bash
pkgmgr archive docs/requirements
```

Pass `--dry-run` to preview, `--include-template` to also archive
`000-template.md`. See `pkgmgr archive --help` for the full surface.

The lint test that fails when a requirement file is fully checked off
([tests/lint/repository/documentation/test_requirements_completeness.py](../../../tests/lint/repository/documentation/test_requirements_completeness.py))
still lives here. It now imports the archive primitives from
`pkgmgr.actions.archive`, pulled in via the `dev` extra in
[pyproject.toml](../../../pyproject.toml).
