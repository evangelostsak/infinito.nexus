#!/usr/bin/env python3
"""CLI entrypoint: list and aggregate the compose services of a role and its
shared dependencies, with optional variant overlay, depth limit, filtering and
ordering. Collection / aggregation / query / rendering live in sibling modules."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from . import PROJECT_ROOT

sys.path.insert(0, str(PROJECT_ROOT))

from utils.cache.applications import get_variants
from utils.roles.applications.services.registry import (
    build_service_registry_from_applications,
    load_applications_from_roles_dir,
)
from utils.roles.applications.services.resources import (
    SUMMABLE_FIELDS,
    aggregate,
    collect_role_resources,
)

from .query import apply_filters, apply_order
from .render import DEFAULT_TOTAL_LABEL, render_json, render_text

ROLES_DIR = PROJECT_ROOT / "roles"


def _resolve_order(tokens: list[str] | None) -> tuple[str, str] | None:
    if not tokens:
        return None
    if len(tokens) == 1:
        return ("asc", tokens[0])
    direction, field = tokens[0].lower(), tokens[1]
    if direction not in ("asc", "desc"):
        raise SystemExit(f"--order direction must be asc|desc, got '{tokens[0]}'")
    return (direction, field)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "List and aggregate the compose services of an Ansible role and its "
            "shared dependencies (resolved recursively via the service registry). "
            "mem_reservation/mem_limit are summed, pids_limit is summed as a "
            "max-provisioned host-pid budget, cpus is max."
        )
    )
    parser.add_argument(
        "--role",
        required=True,
        help="Role name (directory under roles/), e.g. web-app-peertube",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "--order",
        nargs="+",
        metavar="[asc|desc] FIELD",
        help="Order rows by FIELD. FIELD is one of service, role, depth, bond, "
        "mem_reservation, mem_limit, pids_limit, cpus. Direction defaults to asc.",
    )
    parser.add_argument(
        "--filter",
        metavar="EXPR",
        help="Filter rows, e.g. 'bond<=0.5 & cpus>=1 & mem_limit>=512m'. Fields: "
        "bond, depth, mem_reservation, mem_limit, pids_limit, cpus. Operators: "
        "<= >= < > == != ; combine with '&'.",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=0,
        help="Max recursion depth over parent/shared services (0 = unlimited). "
        "1 = the role's own services only.",
    )
    parser.add_argument(
        "--variant",
        type=int,
        default=None,
        help="Variant index from the role's meta/variants.yml (default: base "
        "config). Applies the same variant overlay as inventory creation.",
    )
    parser.add_argument(
        "--sum",
        nargs="*",
        metavar="FIELD",
        default=None,
        help="Show a SUM row instead of the default total. Bare --sum sums all "
        "fields (mem_reservation, mem_limit, pids_limit, cpus, bond); pass field "
        "names to sum only those.",
    )
    parser.add_argument(
        "--unshared",
        action="store_true",
        help="List every service occurrence individually instead of loading each "
        "service only once (the default deduplicates shared services).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    order = _resolve_order(args.order)

    applications = load_applications_from_roles_dir(ROLES_DIR)
    warnings: list[str] = []

    if args.variant is not None:
        app_variants = get_variants(roles_dir=str(ROLES_DIR)).get(args.role) or []
        if 0 <= args.variant < len(app_variants):
            applications = dict(applications)
            applications[args.role] = app_variants[args.variant] or {}
        else:
            warnings.append(
                f"variant {args.variant} out of range for '{args.role}' "
                f"({len(app_variants)} variant(s)); using base config"
            )

    service_registry = build_service_registry_from_applications(applications)

    rows: list[dict[str, Any]] = []
    collect_role_resources(
        role_name=args.role,
        applications=applications,
        service_registry=service_registry,
        visited=set(),
        rows=rows,
        warnings=warnings,
        max_depth=args.depth,
        dedup=not args.unshared,
    )

    try:
        rows = apply_filters(rows, args.filter)
    except ValueError as exc:
        raise SystemExit(f"--filter: {exc}") from exc

    try:
        totals = aggregate(rows, sum_fields=args.sum)
    except ValueError as exc:
        raise SystemExit(f"--sum: {exc}") from exc

    if args.sum is None:
        total_label = DEFAULT_TOTAL_LABEL
    else:
        total_label = "SUM (" + ", ".join(args.sum or sorted(SUMMABLE_FIELDS)) + ")"

    presorted = False
    if order is not None:
        try:
            rows = apply_order(rows, order[0], order[1])
        except ValueError as exc:
            raise SystemExit(f"--order: {exc}") from exc
        presorted = True

    if args.format == "json":
        print(render_json(args.role, rows, totals, warnings))
    else:
        print(
            render_text(
                args.role,
                rows,
                totals,
                warnings,
                presorted=presorted,
                total_label=total_label,
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
