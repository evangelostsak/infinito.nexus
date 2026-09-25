"""Swarm variant-matrix round orchestrator.

Mirrors the compose matrix deploy (``cli.administration.deploy.development.deploy``)
for the swarm test cluster: for each variant round of the primary app it
provisions a per-round inventory (baking that round's ``meta/variants.yml``
overlay into ``host_vars`` so the deploy sees the round's config, e.g. the
keycloak totp-off variant), extends it with the swarm topology, writes runtime
extras, and deploys via ``cli.administration.deploy.swarm`` (the Playwright e2e
runs in-deploy). Each round mirrors the compose ``--full-cycle``: an initial
deploy then an async update pass, each followed by a convergence + reachability
wait; on the first round the backup + restore DR drill runs between them. Prior
rounds' stacks are purged between rounds.

Runs on the cluster host (the test-deploy-swarm workflow's single orchestrator
step) and reaches the nodes through the existing ``scripts/tests/deploy/swarm``
helpers, which it drives per round via environment variables.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from utils import PROJECT_ROOT
from utils.storage.constrained import host_storage_constrained
from utils.tests.swarm.derive_includes import derive_includes, variant_scope
from utils.tests.swarm.extend_inventory import mesh_enabled
from utils.tests.swarm.run import DISK_FLOOR_MB, run_step
from utils.tests.swarm.write.extras import ensure_swarm_keypairs

_SWARM_DIR = PROJECT_ROOT / "scripts" / "tests" / "deploy" / "swarm"
_SWARM_SCRIPTS = _SWARM_DIR / "routine"
_ROLES_DIR = str(PROJECT_ROOT / "roles")
_SWARM_EXTRAS_VARS = "inventories/development/swarm.yml"
_MESH_NAME = "swarm"
_CONTROLLER = "localhost"
_DEFAULT_ADMIN_KEY = "/tmp/swarm-nfs-admin.key"  # noqa: S108 - ephemeral swarm-test path, overridable via KEY_PATH
_DEFAULT_INVENTORY_DIR = "/tmp/inv"  # noqa: S108 - ephemeral swarm-test inventory base in CI


def _provision(
    *, app_id: str, inv_dir: str, round_variants: dict[str, int], vars_payload: dict
) -> int:
    env = os.environ.copy()
    env["APP_ID"] = app_id
    env["INFINITO_INVENTORY_DIR"] = inv_dir
    env["INFINITO_APP_VARIANTS"] = json.dumps(round_variants, sort_keys=True)
    env["INFINITO_VARS_PAYLOAD"] = json.dumps(vars_payload, sort_keys=True)
    return run_step(
        ["bash", str(_SWARM_SCRIPTS / "02_provision_inventory.sh")],
        env=env,
        label=f"provision inventory ({inv_dir})",
    )


def _extend_inventory(
    *, app_id: str, inv_dir: str, round_variants: dict[str, int]
) -> int:
    env = os.environ.copy()
    env["APP_ID"] = app_id
    env["INV_PATH"] = f"{inv_dir}/devices.yml"
    env["INFINITO_APP_VARIANTS"] = json.dumps(round_variants, sort_keys=True)
    return run_step(
        ["python3", "-m", "utils.tests.swarm.extend_inventory"],
        env=env,
        label="extend inventory (workers + group memberships)",
    )


def _write_mesh(*, inv_dir: str) -> int:
    """Write the WireGuard meshes over both inventories of the round.

    Ordered after extend_inventory, which creates the groups the meshes
    resolve from and the sibling backup.yml the data mesh spans. A no-op when
    the run's vpn axis is off, because the groups are then absent entirely.
    """
    if not mesh_enabled():
        return 0
    args = ["--inventory", f"{inv_dir}/devices.yml"]
    args += ["--inventory", f"{inv_dir}/backup.yml"]
    args += ["--host-vars-dir", f"{inv_dir}/host_vars"]
    args += ["--vault-password-file", f"{inv_dir}/.password"]
    args += ["--controller", _CONTROLLER, "--controller-mesh", _MESH_NAME]
    return run_step(
        ["python3", "-m", "cli.administration.inventory.mesh", *args],
        env=os.environ.copy(),
        label="write wireguard meshes (cross-host credentials)",
    )


def _switch_to_mesh(*, inv_dir: str) -> int:
    """Point the inventory at the mesh before the pass that must use it.

    The first pass reaches the nodes over the container connection, because it
    is what brings the mesh up. Every pass after it connects over the mesh, so
    a broken tunnel fails the deploy at the connection instead of letting a
    role quietly fall back to the underlay.
    """
    if not mesh_enabled():
        return 0
    from cli.administration.inventory.mesh.transport import switch_to_mesh

    host_vars = Path(inv_dir) / "host_vars"
    hosts = sorted(path.stem for path in host_vars.glob("*.yml"))
    switched = switch_to_mesh(
        host_vars,
        hosts,
        _MESH_NAME,
        user="administrator",
        private_key_file=os.environ.get("KEY_PATH") or _DEFAULT_ADMIN_KEY,
    )
    for host, address in sorted(switched.items()):
        print(f"[INFO] {host}: ansible now connects over {address}", flush=True)
    if not switched:
        print("[FATAL] no host holds a mesh address to switch to", file=sys.stderr)
        return 1
    return 0


def _force_shared_db(*, inv_dir: str) -> int:
    env = os.environ.copy()
    env["INV_DIR"] = inv_dir
    return run_step(
        ["python3", "-m", "utils.tests.swarm.force_shared_db"],
        env=env,
        label="force shared DB (swarm: embedded DB is compose-only)",
    )


def _write_extras(*, extras_path: str) -> int:
    env = os.environ.copy()
    env["OUT_PATH"] = extras_path
    return run_step(
        ["python3", "-m", "utils.tests.swarm.write.extras"],
        env=env,
        label=f"write runtime extras ({extras_path})",
    )


def _reset_credentials(
    *, app_id: str, inv_dir: str, round_variants: dict[str, int]
) -> int:
    """Regenerate the round's credentials so the update pass has to carry them.

    `administrator` stays exempt: its password is `ansible_become_password`,
    and rotating it would lock the deploy out of the nodes it manages.

    The credential scope is `derive_includes`, the same source
    `02_provision_inventory.sh` feeds provision's `--include`, so the gate
    rotates the ids the round provisioned. A matrix host_vars file also holds
    an application block per mirror artefact, and rotating those costs one
    subprocess each for credentials provision never generated. Every declared
    user password still rotates, so PASS 2 has to carry all of them.
    """
    return run_step(
        [
            "python3",
            "-m",
            "cli.administration.inventory.credentials.reset",
            "--inventory-dir",
            inv_dir,
            "--host",
            os.environ["MGR"],
            "--schema",
            "--users",
            "--include",
            *derive_includes(app_id, variants=round_variants),
            "--app-variants",
            json.dumps(round_variants, sort_keys=True),
            "--mirror",
            "--backup",
            "--except",
            "administrator",
        ],
        env=os.environ.copy(),
        label="reset credentials (rotation gate before the async pass)",
    )


def _deploy(
    *,
    app_id: str,
    inv_dir: str,
    extras_path: str,
    round_index: int,
    total: int,
    update_pass: bool = False,
) -> int:
    env = os.environ.copy()
    env["APP_ID"] = app_id
    cmd = [
        "python3",
        "-m",
        "cli.administration.deploy.swarm",
        f"{inv_dir}/devices.yml",
        "-p",
        f"{inv_dir}/.password",
        "--skip-build",
        "--skip-cleanup",
        "--skip-backup",
        "-e",
        f"@{_SWARM_EXTRAS_VARS}",
        "-e",
        f"@{extras_path}",
        "-e",
        f"VARIANT_INDEX={json.dumps(round_index)}",
    ]
    pass_label = (
        f"matrix-deploy: round {round_index + 1}/{total} "
        f"variants=[{round_index}] apps=['{app_id}']"
    )
    if update_pass:
        cmd += ["-e", "ASYNC_ENABLED=true"]
        label = f"update pass (round {round_index + 1}/{total})"
        print(f"=== {pass_label} PASS 2 (async) ===", flush=True)
    else:
        label = f"deploy round {round_index + 1}/{total}"
        print(f"=== {pass_label} PASS 1 (sync) ===", flush=True)
    return run_step(env=env, cmd=cmd, label=label)


def _deploy_backup_host(*, app_id: str, inv_dir: str, extras_path: str) -> int:
    env = os.environ.copy()
    env["APP_ID"] = app_id
    cmd = [
        "python3",
        "-m",
        "cli.administration.deploy.dedicated",
        f"{inv_dir}/backup.yml",
        "-p",
        f"{inv_dir}/.password",
        "--skip-build",
        "--skip-cleanup",
        "--skip-backup",
        "-e",
        f"@{_SWARM_EXTRAS_VARS}",
        "-e",
        f"@{extras_path}",
    ]
    return run_step(env=env, cmd=cmd, label="deploy backup host (backup.yml)")


def _converge_and_verify(*, app_id: str) -> int:
    env = os.environ.copy()
    env["APP_ID"] = app_id
    rc = run_step(
        ["bash", str(_SWARM_SCRIPTS / "03_wait_converge.sh")],
        env=env,
        label="wait for stack convergence",
    )
    if rc != 0:
        return rc
    return run_step(
        ["bash", str(_SWARM_SCRIPTS / "04_verify_reachable.sh")],
        env=env,
        label="verify reachability",
    )


def _backup_restore_drill(*, app_id: str, inv_dir: str, extras_path: str) -> int:
    env = os.environ.copy()
    env["APP_ID"] = app_id
    env["INFINITO_INVENTORY_DIR"] = inv_dir
    env["DRILL_EXTRAS"] = extras_path
    env["DISK_FLOOR_MB"] = str(DISK_FLOOR_MB)
    return run_step(
        ["bash", str(_SWARM_SCRIPTS / "backup" / "base.sh")],
        env=env,
        label="backup + restore DR drill",
    )


def _verify_recovered_marker(*, app_id: str) -> int:
    env = os.environ.copy()
    env["APP_ID"] = app_id
    return run_step(
        ["bash", str(_SWARM_SCRIPTS / "backup" / "verify_recovered_marker.sh")],
        env=env,
        label="verify recovered marker (post update pass)",
    )


def _purge(*, purge_set: tuple[str, ...]) -> int:
    if not purge_set:
        return 0
    env = os.environ.copy()
    env["apps"] = ",".join(purge_set)
    return run_step(
        ["bash", str(_SWARM_DIR / "utils" / "clean" / "purge_stacks.sh")],
        env=env,
        label=f"purge prior-round stacks ({', '.join(purge_set)})",
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    from cli.administration.deploy.development.variant_select import add_variant_args

    p = argparse.ArgumentParser(
        prog="utils.tests.swarm.matrix",
        description=(
            "Iterate the variant-matrix rounds of one application against the "
            "live swarm test cluster."
        ),
    )
    p.add_argument(
        "--id",
        "--app",
        dest="app",
        default=os.environ.get("APP_ID"),
        help="Primary application id (default: $APP_ID).",
    )
    p.add_argument(
        "--inventory-dir",
        default=os.environ.get(
            "INFINITO_INVENTORY_DIR", _DEFAULT_INVENTORY_DIR
        ),  # nocheck: swarm-test base; matrix sets it per round, compose resolves the key via its own handler
        help=(
            "Base inventory dir; the planner derives per-round folders "
            "<dir>-<n> (default: $INFINITO_INVENTORY_DIR or /tmp/inv)."
        ),
    )
    add_variant_args(p, action="deploy")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    app_id = (args.app or "").strip()
    if not app_id:
        raise SystemExit("swarm-matrix: no application id (set $APP_ID or pass --id)")

    from cli.administration.deploy.development.inventory import (
        _bake_overrides,
        _resolve_variant_payloads,
        plan_dev_inventory_matrix,
    )
    from cli.administration.deploy.development.variant_select import (
        apply_variant_filter,
    )

    plan = plan_dev_inventory_matrix(
        roles_dir=_ROLES_DIR,
        primary_apps=[app_id],
        base_inventory_dir=str(args.inventory_dir),
    )
    try:
        plan = apply_variant_filter(plan, args)
    except ValueError as exc:
        raise SystemExit(f"--variant: {exc}") from exc

    total = len(plan)
    rc = 0
    for plan_index, (
        round_index,
        inv_dir,
        round_variants,
        _round_include,
        round_purge_set,
    ) in enumerate(plan):
        inv_root = inv_dir.rstrip("/")

        if plan_index > 0:
            rc = _purge(purge_set=round_purge_set)
            if rc != 0:
                return rc

        variant_payloads = _resolve_variant_payloads(
            roles_dir=_ROLES_DIR,
            include=variant_scope(app_id, variants=round_variants),
            active_variants=round_variants,
        )
        from utils.tests.swarm.backup_repos import backup_provider_ips
        from utils.tests.swarm.write.extras import backup_applications_overrides

        providers = backup_provider_ips(
            app_id=app_id,
            variants=round_variants,
            manager=os.environ["MGR_IP"],
            nfs_server=os.environ["NFS_IP"],
        )
        print(
            f"=== swarm-matrix: remote-2-local backup providers "
            f"(round {round_index}): {', '.join(providers)} ===",
            flush=True,
        )
        pubkeys = ensure_swarm_keypairs()
        vars_payload = _bake_overrides(
            base_overrides={
                "applications": backup_applications_overrides(providers),
                "users": {
                    name: {"authorized_keys": [key]} for name, key in pubkeys.items()
                },
                "STORAGE_CONSTRAINED": host_storage_constrained(
                    [app_id], round_variants, local_vantage="/"
                ),
            },
            variant_payloads=variant_payloads,
        )
        extras_path = f"{inv_root}/swarm-nfs-extras.yml"

        rc = _provision(
            app_id=app_id,
            inv_dir=inv_root,
            round_variants=round_variants,
            vars_payload=vars_payload,
        )
        if rc == 0:
            rc = _force_shared_db(inv_dir=inv_root)
        if rc == 0:
            rc = _extend_inventory(
                app_id=app_id, inv_dir=inv_root, round_variants=round_variants
            )
        if rc == 0:
            rc = _write_mesh(inv_dir=inv_root)
        if rc == 0:
            rc = _write_extras(extras_path=extras_path)
        if rc == 0:
            rc = _deploy(
                app_id=app_id,
                inv_dir=inv_root,
                extras_path=f"{inv_root}/swarm-nfs-extras.deploy.yml",
                round_index=round_index,
                total=total,
            )
        if rc == 0:
            rc = _converge_and_verify(app_id=app_id)
        if rc == 0 and round_index == 0:
            rc = _deploy_backup_host(
                app_id=app_id,
                inv_dir=inv_root,
                extras_path=f"{inv_root}/swarm-nfs-extras.deploy.yml",
            )
        if rc == 0 and round_index == 0:
            rc = _backup_restore_drill(
                app_id=app_id, inv_dir=inv_root, extras_path=extras_path
            )
        if rc == 0:
            rc = _reset_credentials(
                app_id=app_id, inv_dir=inv_root, round_variants=round_variants
            )
        if rc == 0:
            rc = _write_mesh(inv_dir=inv_root)
        if rc == 0:
            rc = _switch_to_mesh(inv_dir=inv_root)
        if rc == 0:
            rc = _deploy(
                app_id=app_id,
                inv_dir=inv_root,
                extras_path=f"{inv_root}/swarm-nfs-extras.deploy.yml",
                round_index=round_index,
                total=total,
                update_pass=True,
            )
        if rc == 0:
            rc = _converge_and_verify(app_id=app_id)
        if rc == 0 and round_index == 0:
            rc = _verify_recovered_marker(app_id=app_id)
        if rc != 0:
            return rc

    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
