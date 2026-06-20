"""Filter and order the collected service rows by their numeric/scalar fields
(bond, depth, the resource columns) and by service/role."""

from __future__ import annotations

import operator
import re
from typing import TYPE_CHECKING, Any

from .parse import _parse_cpus, _parse_int, _parse_mem_bytes

if TYPE_CHECKING:
    from collections.abc import Callable

_FIELD_ACCESSORS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "service": lambda r: r.get("service"),
    "role": lambda r: r.get("role"),
    "depth": lambda r: r.get("depth"),
    "bond": lambda r: r.get("bond_float"),
    "mem_reservation": lambda r: r.get("mem_reservation_bytes"),
    "mem_limit": lambda r: r.get("mem_limit_bytes"),
    "pids_limit": lambda r: r.get("pids_limit_int"),
    "cpus": lambda r: r.get("cpus_float"),
}

_OPS: dict[str, Callable[[Any, Any], bool]] = {
    "<=": operator.le,
    ">=": operator.ge,
    "!=": operator.ne,
    "==": operator.eq,
    "=": operator.eq,
    "<": operator.lt,
    ">": operator.gt,
}

_FILTER_RE = re.compile(r"^\s*([a-z_]+)\s*(<=|>=|!=|==|=|<|>)\s*(.+?)\s*$")


def _parse_filter_value(field: str, raw: str) -> Any:
    if field in ("mem_reservation", "mem_limit"):
        value = _parse_mem_bytes(raw)
    elif field in ("pids_limit", "depth"):
        value = _parse_int(raw)
    else:
        value = _parse_cpus(raw)
    if value is None:
        raise ValueError(f"invalid value {raw!r} for filter field '{field}'")
    return value


def apply_filters(rows: list[dict[str, Any]], expr: str | None) -> list[dict[str, Any]]:
    if not expr:
        return rows
    conditions: list[tuple[str, Callable[[Any, Any], bool], Any]] = []
    for part in expr.split("&"):
        if not part.strip():
            continue
        match = _FILTER_RE.match(part)
        if not match:
            raise ValueError(f"invalid filter expression: {part.strip()!r}")
        field, op, raw_value = match.group(1), match.group(2), match.group(3)
        if field not in _FIELD_ACCESSORS or field in ("service", "role"):
            raise ValueError(f"unknown numeric filter field: '{field}'")
        conditions.append((field, _OPS[op], _parse_filter_value(field, raw_value)))

    out: list[dict[str, Any]] = []
    for row in rows:
        keep = True
        for field, op_fn, value in conditions:
            cell = _FIELD_ACCESSORS[field](row)
            if cell is None or not op_fn(cell, value):
                keep = False
                break
        if keep:
            out.append(row)
    return out


def _order_key(value: Any) -> tuple[int, float, str]:
    if value is None:
        return (1, 0.0, "")
    if isinstance(value, (int, float)):
        return (0, float(value), "")
    return (0, 0.0, str(value))


def apply_order(
    rows: list[dict[str, Any]], direction: str, field: str
) -> list[dict[str, Any]]:
    if field not in _FIELD_ACCESSORS:
        raise ValueError(f"unknown order field: '{field}'")
    accessor = _FIELD_ACCESSORS[field]
    present = [r for r in rows if accessor(r) is not None]
    missing = [r for r in rows if accessor(r) is None]
    present.sort(key=lambda r: _order_key(accessor(r)), reverse=direction == "desc")
    return present + missing
