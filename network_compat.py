"""Network compatibility helpers for unreliable dual-stack Windows routes.

Tradysquid's local Windows host has repeatedly timed out on GitHub and Discord
while browser traffic remained usable. The affected calls use Git/libcurl and
Requests/urllib3, so the application explicitly prefers IPv4 for those paths.

Set TRADYSQUID_FORCE_IPV4=false to restore normal dual-stack behavior.
"""

from __future__ import annotations

import os
import socket
from typing import Any


_FALSE_VALUES = {"0", "false", "no", "off"}
_INSTALLED = False
_ORIGINAL_ALLOWED_GAI_FAMILY: Any = None


def force_ipv4_enabled() -> bool:
    value = os.environ.get("TRADYSQUID_FORCE_IPV4", "true").strip().casefold()
    return value not in _FALSE_VALUES


def install(*, force: bool | None = None) -> bool:
    """Force Requests/urllib3 DNS selection to IPv4 when enabled.

    The patch affects only this Python process and its Requests traffic. It does
    not disable IPv6 in Windows or alter unrelated applications.
    """
    global _INSTALLED, _ORIGINAL_ALLOWED_GAI_FAMILY
    enabled = force_ipv4_enabled() if force is None else bool(force)
    if not enabled:
        return False

    import urllib3.util.connection as urllib3_connection

    if _ORIGINAL_ALLOWED_GAI_FAMILY is None:
        _ORIGINAL_ALLOWED_GAI_FAMILY = urllib3_connection.allowed_gai_family
    urllib3_connection.allowed_gai_family = lambda: socket.AF_INET
    _INSTALLED = True
    return True


def status() -> dict[str, object]:
    return {
        "enabled": force_ipv4_enabled(),
        "installed": _INSTALLED,
        "address_family": "IPv4" if _INSTALLED else "system-default",
    }
