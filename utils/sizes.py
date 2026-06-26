"""Parse human-readable memory size strings to bytes.

SI/decimal units for the bare suffixes (k=10^3, m=10^6, g=10^9, ...) and IEC
binary for the explicit ``*ib`` suffixes (kib=1024, mib=1024^2, ...). Shared by
the ``node_max_old_space_size`` lookup and the peertube ``install_mem_limit``
filter.
"""

from __future__ import annotations

import re

from ansible.errors import AnsibleFilterError

_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kmgtp]?i?b?)?\s*$", re.IGNORECASE)
_MULT = {
    "": 1,
    "b": 1,
    "k": 10**3,
    "kb": 10**3,
    "m": 10**6,
    "mb": 10**6,
    "g": 10**9,
    "gb": 10**9,
    "t": 10**12,
    "tb": 10**12,
    "p": 10**15,
    "pb": 10**15,
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
    "tib": 1024**4,
    "pib": 1024**5,
}


def to_bytes(val):
    """Convert a numeric or string size (e.g. '512m', '2GiB', 1024) to bytes.

    Returns None for None/empty input. Raises AnsibleFilterError on an unparseable value.
    """
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return int(val)
    if not isinstance(val, str):
        raise AnsibleFilterError(
            f"to_bytes: unsupported size type: {type(val).__name__}"
        )
    m = _SIZE_RE.match(val)
    if not m:
        raise AnsibleFilterError(f"to_bytes: unrecognized size string: {val!r}")
    num = float(m.group(1))
    unit = (m.group(2) or "").lower()
    if unit not in _MULT:
        raise AnsibleFilterError(f"to_bytes: unknown unit in size: {unit!r}")
    return int(num * _MULT[unit])
