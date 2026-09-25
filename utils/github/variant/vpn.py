"""The WireGuard-mesh axis of a deploy row.

Split out beside ``tor.py`` for the same reason: one axis, its modes, its
rotation and its glyph pairing belong together rather than spread through the
assigner.

A swarm deploy runs either over the mesh or straight over the underlay, and
both have to keep working -- the mesh joins physically separated clusters, so a
single-site swarm has no use for it and must not depend on it. Rotating the
axis proves both arms instead of proving one and assuming the other.
"""

from __future__ import annotations

VPN_DEPLOY_MODES = ("swarm",)
"""Modes the mesh is meaningful in. Compose is a single host, so there is
nothing to tunnel between and the axis is always off there."""

MESH_GLYPH_MODES = VPN_DEPLOY_MODES
"""Modes whose label carries a mesh glyph at all. A compose title stays as it
was, so the existing job names do not all churn for an axis they never take."""


def vpn_states(mode: str) -> list[bool]:
    """The mesh states *mode* is worth running for a priority row."""
    return [False, True] if mode in VPN_DEPLOY_MODES else [False]


def wants_vpn(position: int, sweep: int) -> bool:
    """Whether a swarm row carries the mesh this sweep.

    Quartered on ``sweep // 4`` so it flips in step with neither the mode
    rotation nor the onion: a row walks every mode/tor/vpn combination over
    eight sweeps instead of re-proving the same pairing.
    """
    return (position + sweep // 4) % 2 == 0


def rotated_vpn(
    mode: str, *, position: int, sweep: int, pin: bool | None = None
) -> bool:
    """The single mesh state a regular row takes this sweep."""
    if mode not in VPN_DEPLOY_MODES:
        return False
    if pin is not None:
        return pin
    return wants_vpn(position, sweep)
