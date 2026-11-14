"""Local-only, qualitative Mutagen sync performance guidance."""

from __future__ import annotations

import ntpath
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_LOCAL_PROTOCOLS = (0, "local")
_DEFAULT_POLLING_SECONDS = 10
_WRITE_SIDES = {
    "two-way-safe": {"alpha", "beta"},
    "two-way-resolved": {"alpha", "beta"},
    "one-way-safe": {"beta"},
    "one-way-replica": {"beta"},
}


def _is_network_path(path: str | Path) -> bool:
    drive, _tail = ntpath.splitdrive(os.fspath(path))
    return drive.startswith(("\\\\", "//"))


def _path_device(path: str | Path) -> int | None:
    """Read a path's device from itself or its nearest existing parent."""
    if _is_network_path(path):
        return None
    candidate = Path(path).expanduser()
    try:
        while not candidate.exists():
            parent = candidate.parent
            if parent == candidate:
                return None
            candidate = parent
        return candidate.stat().st_dev
    except OSError:
        return None


def _inspect_local_root(
    side: str,
    endpoint: Mapping[str, Any],
    *,
    mode: str | None,
    mutagen_data_dir: Path,
    session_stage_mode: str,
) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
    raw_path = endpoint.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return [{"code": "local_root_unreported", "side": side}], None
    if _is_network_path(raw_path):
        return [{"code": "local_root_network_uninspected", "side": side}], None

    root = Path(raw_path).expanduser()
    warnings: list[dict[str, str]] = []
    try:
        is_symlink = root.is_symlink()
        is_junction_method = getattr(root, "is_junction", None)
        is_junction = bool(is_junction_method()) if callable(is_junction_method) else False
    except OSError:
        # Link status is a safety boundary: don't follow a path whose status
        # could not be checked.
        return [{"code": "local_root_unreadable", "side": side}], None
    if is_symlink or is_junction:
        warnings.append({"code": "local_root_symlink", "side": side})
        return warnings, None
    try:
        root_info = root.stat()
    except FileNotFoundError:
        warnings.append({"code": "local_root_missing", "side": side})
        return warnings, None
    except OSError:
        warnings.append({"code": "local_root_unreadable", "side": side})
        return warnings, None

    is_directory = stat.S_ISDIR(root_info.st_mode)
    try:
        readable = os.access(root, os.R_OK) and (not is_directory or os.access(root, os.X_OK))
        writable = os.access(root, os.W_OK) if side in _WRITE_SIDES.get(mode or "", set()) else True
    except OSError:
        readable = False
        writable = False
    if not readable:
        warnings.append({"code": "local_root_unreadable", "side": side})
    if not writable:
        warnings.append({"code": "local_root_unwritable", "side": side})

    stage_mode = endpoint.get("stageMode", session_stage_mode)
    if stage_mode == "mutagen":
        if _is_network_path(mutagen_data_dir):
            warnings.append({"code": "staging_path_network_uninspected", "side": side})
            return warnings, None
        root_device = _path_device(root)
        stage_device = _path_device(mutagen_data_dir)
        if root_device is not None and stage_device is not None and root_device != stage_device:
            warnings.append({"code": "cross_filesystem_staging", "side": side})
            return warnings, {"key": f"{side}.stageMode", "value": "neighboring"}
    return warnings, None


def analyze_sync_session(
    session: Mapping[str, Any] | None,
    *,
    mutagen_data_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Return advisory text keys, local proposal values, and bounded path findings.

    This function never changes the session, walks a filesystem tree, or contacts
    Mutagen. Missing native values remain unknown.
    """
    if not isinstance(session, Mapping):
        session = {}

    environment_data_dir = os.environ.get("MUTAGEN_DATA_DIRECTORY")
    data_dir = Path(
        mutagen_data_dir or environment_data_dir or (Path.home() / ".mutagen")
    ).expanduser()
    watch = session.get("watch")
    watch = watch if isinstance(watch, Mapping) else {}
    watch_mode = watch.get("mode") if isinstance(watch.get("mode"), str) else None
    interval = watch.get("pollingInterval")
    scan_mode = session.get("scanMode") if isinstance(session.get("scanMode"), str) else None
    raw_session_stage_mode = session.get("stageMode")
    session_stage_mode = (
        raw_session_stage_mode if isinstance(raw_session_stage_mode, str) else "mutagen"
    )
    mode = session.get("mode") if isinstance(session.get("mode"), str) else None

    warnings: list[dict[str, str]] = []
    recommendations: dict[str, Any] = {}
    guidance = ["entry_count_unknown", "large_root_scan_cost"]

    if watch_mode == "force-poll":
        if isinstance(interval, int) and not isinstance(interval, bool) and interval > 0:
            if interval < _DEFAULT_POLLING_SECONDS:
                warnings.append({"code": "high_frequency_polling", "seconds": str(interval)})
                recommendations["watch.mode"] = "portable"
        else:
            warnings.append({"code": "polling_interval_unknown"})

    if watch_mode != "no-watch" and scan_mode == "full":
        warnings.append({"code": "full_scan_large_roots"})
        recommendations["scanMode"] = "accelerated"

    for side in ("alpha", "beta"):
        endpoint = session.get(side)
        if not isinstance(endpoint, Mapping) or endpoint.get("protocol") not in _LOCAL_PROTOCOLS:
            continue
        endpoint_warnings, stage_recommendation = _inspect_local_root(
            side,
            endpoint,
            mode=mode,
            mutagen_data_dir=data_dir,
            session_stage_mode=session_stage_mode,
        )
        warnings.extend(endpoint_warnings)
        if stage_recommendation:
            recommendations[stage_recommendation["key"]] = stage_recommendation["value"]

    unsafe_roots = {
        "local_root_unreported",
        "local_root_symlink",
        "local_root_missing",
        "local_root_unreadable",
        "local_root_unwritable",
    }
    if any(warning["code"] in unsafe_roots for warning in warnings):
        recommendations.pop("watch.mode", None)
        recommendations.pop("scanMode", None)

    return {
        "recommendations": recommendations,
        "warnings": warnings,
        "guidance": guidance,
        "entry_count": None,
        "measured_performance": False,
        "remote_inspection": False,
    }
