# Pull Request Resolvers 🔀

This directory contains Pull Request-specific resolver scripts used by the PR workflow.

Examples in this folder:

- `scope.sh` resolves whether a Pull Request is agents-only, documentation-only, or full scope
- `branch_prefix.sh` validates that the PR branch prefix matches the detected scope; see [branch.md](../../../../docs/contributing/artefact/git/branch.md) for the authoritative list of valid prefixes and their CI impact
- `merge_ref.sh` resolves the merge ref used for forked PR workflows
- `subset_roles.py` parses the `roles:` block from the PR body when the `🧩 Subset` label is set, validates the ids against `roles/`, and emits the restricted whitelist; see the "Subset label" section in [pipeline.md](../../../../docs/contributing/artefact/git/pipeline.md)

These scripts keep PR scope detection, branch-prefix validation, fork merge-ref resolution, and subset-label parsing together in one place.
