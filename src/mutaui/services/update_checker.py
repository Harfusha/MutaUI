"""Opt-in, read-only check for a published MutaUI release."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

API_URL = "https://api.github.com/repos/Harfusha/MutaUI/releases/latest"
RELEASES_URL = "https://github.com/Harfusha/MutaUI/releases"
MAX_RESPONSE_BYTES = 64 * 1024
TIMEOUT_SECONDS = 5
_VERSION_PATTERN = re.compile(r"^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


class UpdateCheckError(ValueError):
    """Raised when the release response cannot be safely interpreted."""


class _GitHubRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Any:
        target = urlsplit(newurl)
        if (
            target.scheme != "https"
            or target.hostname != "api.github.com"
            or target.path != "/repos/Harfusha/MutaUI/releases/latest"
        ):
            raise UpdateCheckError("unexpected redirect host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass(frozen=True)
class UpdateCheckResult:
    latest_version: str | None
    available: bool
    release_url: str | None


def _parse_version(value: object) -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise UpdateCheckError("release version is invalid")
    match = _VERSION_PATTERN.fullmatch(value)
    if match is None:
        raise UpdateCheckError("release version is invalid")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def check_for_update(
    *,
    current_version: str,
    enabled: bool,
    opener: Callable[..., Any] | None = None,
) -> UpdateCheckResult:
    """Fetch public release metadata only when update checks are enabled."""
    if not enabled:
        return UpdateCheckResult(latest_version=None, available=False, release_url=None)

    current = _parse_version(current_version)
    request = Request(
        API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"MutaUI-update-checker/{current_version}",
        },
    )
    open_url = opener or build_opener(_GitHubRedirectHandler()).open
    try:
        with open_url(request, timeout=TIMEOUT_SECONDS) as response:
            response_url = urlsplit(response.geturl())
            if (
                response_url.scheme != "https"
                or response_url.hostname != "api.github.com"
                or response_url.path != "/repos/Harfusha/MutaUI/releases/latest"
            ):
                raise UpdateCheckError("unexpected response host")
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except UpdateCheckError:
        raise
    except Exception as exc:
        raise UpdateCheckError("release check failed") from exc

    if len(body) > MAX_RESPONSE_BYTES:
        raise UpdateCheckError("release response is too large")
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateCheckError("release response is invalid") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("draft") is not False
        or payload.get("prerelease") is not False
    ):
        raise UpdateCheckError("release response is invalid")

    tag = payload.get("tag_name")
    if not isinstance(tag, str):
        raise UpdateCheckError("release version is invalid")
    latest = _parse_version(tag)
    latest_version = tag.removeprefix("v")
    available = latest > current
    release_url = f"{RELEASES_URL}/tag/{tag}" if available else None
    return UpdateCheckResult(
        latest_version=latest_version,
        available=available,
        release_url=release_url,
    )
