"""Interpret raw service-config values: parse resource scalars and evaluate the
enabled/shared/container predicates a service entry exposes."""

from __future__ import annotations

from typing import Any

from humanfriendly import parse_size

_RESOURCE_KEYS = ("mem_reservation", "mem_limit", "pids_limit", "cpus")
_CONTAINER_KEYS = ("image", "name", "version", "container")


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse_mem_bytes(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(parse_size(text))
    except Exception:
        return None


def _parse_cpus(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_bond(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _is_enabled(service_conf: dict[str, Any], default_enabled: bool) -> bool:
    if "enabled" not in service_conf:
        return default_enabled
    raw = service_conf.get("enabled")
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    return text not in ("false", "0", "no", "off")


def _is_shared(service_conf: dict[str, Any]) -> bool:
    raw = service_conf.get("shared", False)
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ("true", "1", "yes", "on")


def _looks_like_container(service_conf: dict[str, Any]) -> bool:
    return any(key in service_conf for key in _RESOURCE_KEYS + _CONTAINER_KEYS)


def _has_resource_keys(service_conf: dict[str, Any]) -> bool:
    return any(key in service_conf for key in _RESOURCE_KEYS)
