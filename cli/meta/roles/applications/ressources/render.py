"""Render the collected service rows and aggregated totals as an aligned text
table or as JSON."""

from __future__ import annotations

import json
from typing import Any

from humanfriendly import format_size


def _fmt_mem(value: int | None) -> str:
    if value is None:
        return "-"
    return format_size(value, binary=False)


def _fmt_int(value: int | None) -> str:
    return "-" if value is None else str(value)


def _fmt_float(value: float | None) -> str:
    if value is None:
        return "-"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


DEFAULT_TOTAL_LABEL = "TOTAL (mem=SUM, pids=SUM max-provisioned, cpus=MAX)"


def render_text(
    role_name: str,
    rows: list[dict[str, Any]],
    totals: dict[str, Any],
    warnings: list[str],
    presorted: bool = False,
    total_label: str = DEFAULT_TOTAL_LABEL,
) -> str:
    headers = [
        "service",
        "role",
        "depth",
        "mem_reservation",
        "mem_limit",
        "pids_limit",
        "cpus",
        "bond",
    ]
    ordered = (
        rows if presorted else sorted(rows, key=lambda r: (r["service"], r["role"]))
    )
    table_rows: list[tuple[str, ...]] = [
        (
            row["service"],
            row["role"],
            _fmt_int(row.get("depth")),
            _fmt_mem(row["mem_reservation_bytes"]),
            _fmt_mem(row["mem_limit_bytes"]),
            _fmt_int(row["pids_limit_int"]),
            _fmt_float(row["cpus_float"]),
            _fmt_float(row.get("bond_float")),
        )
        for row in ordered
    ]

    total_row = (
        total_label,
        "",
        "",
        _fmt_mem(totals["mem_reservation_bytes"]),
        _fmt_mem(totals["mem_limit_bytes"]),
        _fmt_int(totals["pids_limit_int"]),
        _fmt_float(totals["cpus_float"]),
        _fmt_float(totals.get("bond_float")),
    )

    widths = [len(h) for h in headers]
    for r in [*table_rows, total_row]:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    sep = "  ".join("-" * w for w in widths)
    lines = [
        f"# Resources for role: {role_name}",
        "",
        fmt_row(tuple(headers)),
        sep,
    ]
    lines.extend(fmt_row(r) for r in table_rows)
    lines.append(sep)
    lines.append(fmt_row(total_row))

    if warnings:
        lines.append("")
        lines.append("# Warnings")
        lines.extend(f"! {w}" for w in warnings)

    return "\n".join(lines)


def render_json(
    role_name: str,
    rows: list[dict[str, Any]],
    totals: dict[str, Any],
    warnings: list[str],
) -> str:
    def _row(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "depth": row.get("depth"),
            "role": row["role"],
            "service": row["service"],
            "mem_reservation": {
                "raw": row["mem_reservation_raw"],
                "bytes": row["mem_reservation_bytes"],
                "human": _fmt_mem(row["mem_reservation_bytes"]),
            },
            "mem_limit": {
                "raw": row["mem_limit_raw"],
                "bytes": row["mem_limit_bytes"],
                "human": _fmt_mem(row["mem_limit_bytes"]),
            },
            "pids_limit": {
                "raw": row["pids_limit_raw"],
                "value": row["pids_limit_int"],
            },
            "cpus": {
                "raw": row["cpus_raw"],
                "value": row["cpus_float"],
            },
            "bond": {
                "raw": row.get("bond_raw"),
                "value": row.get("bond_float"),
            },
        }

    payload = {
        "role": role_name,
        "services": [_row(r) for r in rows],
        "totals": {
            "mem_reservation": {
                "bytes": totals["mem_reservation_bytes"],
                "human": _fmt_mem(totals["mem_reservation_bytes"]),
            },
            "mem_limit": {
                "bytes": totals["mem_limit_bytes"],
                "human": _fmt_mem(totals["mem_limit_bytes"]),
            },
            "pids_limit": {"value": totals["pids_limit_int"]},
            "cpus": {"value": totals["cpus_float"]},
            "bond": {"value": totals.get("bond_float")},
            "aggregation": {
                "mem_reservation": "sum",
                "mem_limit": "sum",
                "pids_limit": "sum (max-provisioned; per-container cap, not shared load)",
                "cpus": "max",
            },
        },
        "warnings": warnings,
    }
    return json.dumps(payload, indent=2)
