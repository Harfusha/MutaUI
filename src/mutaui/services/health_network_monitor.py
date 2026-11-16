"""Optional Qt network reachability monitoring for session health."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def attach_health_network_monitor(
    on_reachability_changed: Callable[[Any], None],
) -> tuple[Any | None, Any]:
    """Connect Qt reachability changes when the platform backend supports them."""
    information: Any | None = None
    reachability: Any = None
    try:
        from PySide6.QtNetwork import QNetworkInformation

        if not hasattr(QNetworkInformation, "loadDefaultBackend"):
            return None, None
        if not QNetworkInformation.loadDefaultBackend():
            return None, None
        information = QNetworkInformation.instance()
        if information is None or not information.supports(
            QNetworkInformation.Feature.Reachability
        ):
            return None, None
        reachability = information.reachability()
        information.reachabilityChanged.connect(on_reachability_changed)
    except (ImportError, RuntimeError):
        pass
    return information, reachability
