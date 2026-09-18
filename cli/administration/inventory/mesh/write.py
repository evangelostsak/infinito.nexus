"""Project a resolved mesh onto the host_vars of every member.

Each member receives its own private key and the public halves of the peers it
may reach. A private key is written to exactly one file -- the one belonging to
the host that owns it -- so a leaked inventory compromises one member rather
than the mesh.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ruamel.yaml.comments import CommentedMap

from cli.administration.inventory.provision.ruamel_io import (
    dump_document,
    ensure_map,
    load_document,
    vault_value,
)
from utils.manager.credential_key import CREDENTIALS_KEY, SECRETS_KEY

from .keys import is_valid_public_key

if TYPE_CHECKING:
    from pathlib import Path

    from .model import Mesh

# Rationale: the default consumer, not a dependency. Every entry point takes
# the application id as a parameter, so a later role that needs correlated
# secrets reuses this package without editing it.
DEFAULT_APPLICATION_ID = "svc-net-wireguard"
MESHES_KEY = "meshes"
HOST_PREFIX_32 = "/32"


def private_key_name(mesh_name: str) -> str:
    """The credential key a member's own secret half is stored under."""
    return f"mesh_private_key_{mesh_name}"


def host_vars_path(host_vars_dir: Path, host: str) -> Path:
    return host_vars_dir / f"{host}.yml"


def _mesh_entry(document: CommentedMap, mesh_name: str, application_id: str) -> dict:
    return (
        document.get("applications", {})
        .get(application_id, {})
        .get(MESHES_KEY, {})
        .get(mesh_name, {})
    )


def existing_public_keys(
    host_vars_dir: Path,
    hosts: list[str],
    mesh_name: str,
    application_id: str = DEFAULT_APPLICATION_ID,
) -> dict[str, str]:
    """The public keys already issued to ``hosts`` for ``mesh_name``.

    Read from the plaintext mesh entry rather than by decrypting the private
    half, so planning needs no vault password and a re-run never has to
    re-encrypt a secret it would then have to write back.

    A host whose stored credential has gone missing is reported as unkeyed, so
    the pair is reminted together instead of leaving a public key that no
    private key answers for.
    """
    found: dict[str, str] = {}
    for host in hosts:
        path = host_vars_path(host_vars_dir, host)
        if not path.exists():
            continue
        document = load_document(path)
        public_key = _mesh_entry(document, mesh_name, application_id).get("public_key")
        if not isinstance(public_key, str) or not is_valid_public_key(public_key):
            continue
        credentials = (
            document.get("applications", {})
            .get(application_id, {})
            .get(SECRETS_KEY, {})
            .get(CREDENTIALS_KEY, {})
        )
        if private_key_name(mesh_name) not in credentials:
            continue
        found[host] = public_key
    return found


def _peer_entries(mesh: Mesh, host: str) -> list[CommentedMap]:
    entries: list[CommentedMap] = []
    for peer in mesh.peers_of(host):
        entry = CommentedMap()
        entry["host"] = peer.host
        entry["public_key"] = peer.public_key
        entry["address"] = peer.address
        entry["allowed_ips"] = (
            mesh.spec.subnet if peer.is_hub else peer.address + HOST_PREFIX_32
        )
        entry["is_hub"] = peer.is_hub
        entries.append(entry)
    return entries


def write_mesh(
    mesh: Mesh,
    host_vars_dir: Path,
    vault_password_file: Path,
    application_id: str = DEFAULT_APPLICATION_ID,
) -> list[Path]:
    """Write ``mesh`` into every member's host_vars and return the paths."""
    written: list[Path] = []
    key_name = private_key_name(mesh.spec.name)

    for member in mesh.members:
        path = host_vars_path(host_vars_dir, member.host)
        document = load_document(path) if path.exists() else CommentedMap()

        app = ensure_map(ensure_map(document, "applications"), application_id)
        entry = ensure_map(ensure_map(app, MESHES_KEY), mesh.spec.name)
        entry["address"] = member.address
        entry["subnet"] = mesh.spec.subnet
        entry["listen_port"] = mesh.spec.listen_port
        entry["is_hub"] = member.is_hub
        entry["public_key"] = member.public_key
        entry["peers"] = _peer_entries(mesh, member.host)

        if member.private_key is not None:
            credentials = ensure_map(ensure_map(app, SECRETS_KEY), CREDENTIALS_KEY)
            credentials[key_name] = vault_value(
                vault_password_file, member.private_key, key_name
            )

        dump_document(path, document)
        written.append(path)
    return written
