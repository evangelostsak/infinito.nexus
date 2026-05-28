# SSO Tests 🔐

Integration tests that enforce per-role invariants of the unified
``services.sso`` block across roles, including normalization of ``allowed_groups`` paths and
allocation of per-consumer SSO-proxy ports.

Tests in this directory MUST only cover SSO configuration invariants.
Generic port-uniqueness and port-reference-validity rules MUST live
under `tests/integration/ports/`, and domain-related checks MUST live
under `tests/integration/domains/`.

For framework, directory layout, and `make test-integration` usage see
[integration.md](../../../../docs/contributing/actions/testing/integration.md).
