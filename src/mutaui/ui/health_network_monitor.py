import time
from typing import Any


def attach_health_network_monitor(window: Any) -> None:
    try:
        from PySide6.QtNetwork import QNetworkInformation

        if not hasattr(QNetworkInformation, "loadDefaultBackend"):
            return
        if not QNetworkInformation.loadDefaultBackend():
            return
        information = QNetworkInformation.instance()
        if information is None or not information.supports(
            QNetworkInformation.Feature.Reachability
        ):
            return
        window._health_network_information = information
        window._health_network_reachability = information.reachability()
        information.reachabilityChanged.connect(window._health_network_changed)
    except (ImportError, RuntimeError):
        return


def health_network_changed(window: Any, reachability: object) -> None:
    previous = window._health_network_reachability
    window._health_network_reachability = reachability
    if previous is not None and reachability != previous:
        window.health_tracker.note_environment_event("network_change", now=time.monotonic())
