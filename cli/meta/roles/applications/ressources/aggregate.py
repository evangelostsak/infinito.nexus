"""Aggregate per-service resource rows into a single budget.

Default (``sum_fields is None``): mem_reservation / mem_limit are summed,
pids_limit is summed (max-provisioned host-pid budget), cpus is the max (shared
across containers, not additive); bond is not aggregated.

``--sum`` mode (``sum_fields`` is a list): every requested field is summed
(an empty list means all summable fields); unrequested fields stay ``None``."""

from __future__ import annotations

from typing import Any

SUMMABLE_FIELDS: dict[str, str] = {
    "mem_reservation": "mem_reservation_bytes",
    "mem_limit": "mem_limit_bytes",
    "pids_limit": "pids_limit_int",
    "cpus": "cpus_float",
    "bond": "bond_float",
}


def _sum_column(rows: list[dict[str, Any]], column: str) -> Any:
    values = [row.get(column) for row in rows if row.get(column) is not None]
    return sum(values) if values else None


def aggregate(
    rows: list[dict[str, Any]], sum_fields: list[str] | None = None
) -> dict[str, Any]:
    if sum_fields is not None:
        fields = sum_fields or list(SUMMABLE_FIELDS)
        totals: dict[str, Any] = dict.fromkeys(SUMMABLE_FIELDS.values())
        for field in fields:
            column = SUMMABLE_FIELDS.get(field)
            if column is None:
                raise ValueError(f"unknown sum field: '{field}'")
            totals[column] = _sum_column(rows, column)
        return totals

    total_mem_res = 0
    total_mem_lim = 0
    total_pids = 0
    max_cpus = 0.0
    any_mem_res = any_mem_lim = any_pids = any_cpus = False

    for row in rows:
        if row["mem_reservation_bytes"] is not None:
            total_mem_res += row["mem_reservation_bytes"]
            any_mem_res = True
        if row["mem_limit_bytes"] is not None:
            total_mem_lim += row["mem_limit_bytes"]
            any_mem_lim = True
        if row["pids_limit_int"] is not None:
            total_pids += row["pids_limit_int"]
            any_pids = True
        if row["cpus_float"] is not None:
            max_cpus = max(max_cpus, row["cpus_float"])
            any_cpus = True

    return {
        "mem_reservation_bytes": total_mem_res if any_mem_res else None,
        "mem_limit_bytes": total_mem_lim if any_mem_lim else None,
        "pids_limit_int": total_pids if any_pids else None,
        "cpus_float": max_cpus if any_cpus else None,
        "bond_float": None,
    }
