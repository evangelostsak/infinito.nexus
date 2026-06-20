"""Walk a role's services and the shared dependencies it pulls in, emitting one
flat row per service (resolving template-gated shared services to the provider
role's entity via the service registry)."""

from __future__ import annotations

from typing import Any

from utils.roles.entity_name import get_entity_name

from .parse import (
    _as_mapping,
    _has_resource_keys,
    _is_enabled,
    _is_shared,
    _looks_like_container,
    _parse_bond,
    _parse_cpus,
    _parse_int,
    _parse_mem_bytes,
)

_DEFAULT_BOND = 1.0


def _row_for_service(
    role_name: str,
    service_key: str,
    service_conf: dict[str, Any],
    depth: int = 1,
) -> dict[str, Any]:
    bond = _parse_bond(service_conf.get("bond"))
    return {
        "depth": depth,
        "role": role_name,
        "service": service_key,
        "mem_reservation_raw": service_conf.get("mem_reservation"),
        "mem_limit_raw": service_conf.get("mem_limit"),
        "pids_limit_raw": service_conf.get("pids_limit"),
        "cpus_raw": service_conf.get("cpus"),
        "bond_raw": service_conf.get("bond"),
        "mem_reservation_bytes": _parse_mem_bytes(service_conf.get("mem_reservation")),
        "mem_limit_bytes": _parse_mem_bytes(service_conf.get("mem_limit")),
        "pids_limit_int": _parse_int(service_conf.get("pids_limit")),
        "cpus_float": _parse_cpus(service_conf.get("cpus")),
        "bond_float": _DEFAULT_BOND if bond is None else bond,
    }


def collect_role_resources(
    role_name: str,
    applications: dict[str, dict[str, Any]],
    service_registry: dict[str, dict[str, Any]],
    visited: set,
    rows: list[dict[str, Any]],
    warnings: list[str],
    depth: int = 1,
    max_depth: int = 0,
    dedup: bool = True,
    loaded: set | None = None,
) -> None:
    if loaded is None:
        loaded = set()
    if role_name in visited:
        return
    visited.add(role_name)

    if role_name not in applications:
        warnings.append(f"role '{role_name}' has no meta/services.yml; skipping")
        return

    config = _as_mapping(applications[role_name])
    services = _as_mapping(config.get("services"))
    entity_name = get_entity_name(role_name)

    def add(service_key: str, service_conf: dict[str, Any]) -> None:
        if dedup and service_key in loaded:
            return
        loaded.add(service_key)
        rows.append(_row_for_service(role_name, service_key, service_conf, depth))

    if entity_name and entity_name in services:
        add(entity_name, _as_mapping(services.get(entity_name)))
    else:
        warnings.append(
            f"role '{role_name}' has no services.{entity_name or '<entity>'} entry"
        )

    shared_dependencies: list[str] = []
    for service_key, raw_service_conf in services.items():
        if service_key == entity_name:
            continue
        service_conf = _as_mapping(raw_service_conf)
        if not service_conf:
            continue

        if not _is_enabled(
            service_conf, default_enabled=_looks_like_container(service_conf)
        ):
            continue

        provider = _as_mapping(service_registry.get(service_key))
        provider_role = provider.get("role") if provider else None

        if _has_resource_keys(service_conf):
            add(service_key, service_conf)
        elif provider_role and provider_role != role_name:
            shared_dependencies.append(provider_role)
        elif _is_shared(service_conf):
            warnings.append(
                f"{role_name}: shared service '{service_key}' has no registered provider"
            )
        elif _looks_like_container(service_conf):
            add(service_key, service_conf)

    if max_depth != 0 and depth >= max_depth:
        return

    for provider_role in shared_dependencies:
        collect_role_resources(
            provider_role,
            applications,
            service_registry,
            visited,
            rows,
            warnings,
            depth=depth + 1,
            max_depth=max_depth,
            dedup=dedup,
            loaded=loaded,
        )
