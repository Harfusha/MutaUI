from __future__ import annotations

import json
from io import BytesIO
from typing import Any
from urllib.request import Request

import pytest

from mutaui.services.update_checker import (
    UpdateCheckError,
    _GitHubRedirectHandler,
    _parse_version,
    check_for_update,
)
from settings import validate_settings


class _Response:
    def __init__(
        self,
        body: Any,
        *,
        url: str = "https://api.github.com/repos/Harfusha/MutaUI/releases/latest",
    ) -> None:
        self._body = json.dumps(body).encode("utf-8")
        self._url = url

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self._body if size < 0 else self._body[:size]

    def geturl(self) -> str:
        return self._url


def test_release_check_is_disabled_by_default_and_does_not_contact_network() -> None:
    settings = validate_settings({}).values
    calls: list[object] = []

    result = check_for_update(
        current_version="8.2.0",
        enabled=settings["check_updates_on_startup"],
        opener=lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    assert result.available is False
    assert result.latest_version is None
    assert calls == []


def test_enabled_check_reports_new_stable_version_without_trusting_release_url() -> None:
    calls: list[tuple[object, dict[str, object]]] = []

    def opener(request: object, **kwargs: object) -> _Response:
        calls.append((request, kwargs))
        return _Response(
            {
                "tag_name": "v8.3.0",
                "html_url": "https://attacker.example/payload",
                "draft": False,
                "prerelease": False,
            }
        )

    result = check_for_update(current_version="8.2.0", enabled=True, opener=opener)

    assert result.available is True
    assert result.latest_version == "8.3.0"
    assert result.release_url == "https://github.com/Harfusha/MutaUI/releases/tag/v8.3.0"
    assert len(calls) == 1
    assert calls[0][1] == {"timeout": 5}
    request = calls[0][0]
    assert request.full_url == "https://api.github.com/repos/Harfusha/MutaUI/releases/latest"
    assert request.get_header("Authorization") is None
    assert request.get_header("Accept") == "application/vnd.github+json"


def test_same_version_is_not_reported_as_an_update() -> None:
    result = check_for_update(
        current_version="8.3.0",
        enabled=True,
        opener=lambda *_args, **_kwargs: _Response(
            {"tag_name": "8.3.0", "draft": False, "prerelease": False}
        ),
    )

    assert result.available is False
    assert result.latest_version == "8.3.0"


@pytest.mark.parametrize(
    "payload",
    [
        {"tag_name": "v8.3.0-rc.1", "draft": False, "prerelease": False},
        {"tag_name": "v8.3.0", "draft": True, "prerelease": False},
        {"tag_name": "v8.3.0", "draft": False, "prerelease": True},
        {"tag_name": "https://attacker.example/payload", "draft": False, "prerelease": False},
    ],
)
def test_invalid_or_non_stable_release_is_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(UpdateCheckError):
        check_for_update(
            current_version="8.2.0",
            enabled=True,
            opener=lambda *_args, **_kwargs: _Response(payload),
        )


def test_redirect_outside_github_api_is_rejected() -> None:
    with pytest.raises(UpdateCheckError, match="unexpected response host"):
        check_for_update(
            current_version="8.2.0",
            enabled=True,
            opener=lambda *_args, **_kwargs: _Response(
                {"tag_name": "v8.3.0", "draft": False, "prerelease": False},
                url="https://attacker.example/releases/latest",
            ),
        )


def test_redirect_handler_blocks_external_host_before_following_it() -> None:
    handler = _GitHubRedirectHandler()

    with pytest.raises(UpdateCheckError, match="unexpected redirect host"):
        handler.redirect_request(
            None,
            None,
            302,
            "Found",
            {},
            "https://attacker.example/releases/latest",
        )


def test_redirect_handler_allows_same_endpoint() -> None:
    handler = _GitHubRedirectHandler()

    redirected = handler.redirect_request(
        Request("https://api.github.com/repos/Harfusha/MutaUI/releases/latest"),
        BytesIO(b""),
        302,
        "Found",
        {},
        "https://api.github.com/repos/Harfusha/MutaUI/releases/latest",
    )

    assert redirected is not None


def test_release_check_rejects_network_failure_and_invalid_json() -> None:
    def fail(*_args, **_kwargs):
        raise OSError("offline")

    with pytest.raises(UpdateCheckError, match="release check failed"):
        check_for_update(current_version="8.2.0", enabled=True, opener=fail)

    class InvalidJsonResponse(_Response):
        def read(self, size: int = -1) -> bytes:
            return b"not-json"

    with pytest.raises(UpdateCheckError, match="release response is invalid"):
        check_for_update(
            current_version="8.2.0",
            enabled=True,
            opener=lambda *_args, **_kwargs: InvalidJsonResponse({}),
        )


def test_release_check_rejects_oversized_and_non_object_payloads() -> None:
    class LargeResponse(_Response):
        def read(self, size: int = -1) -> bytes:
            return b"x" * size

    with pytest.raises(UpdateCheckError, match="response is too large"):
        check_for_update(
            current_version="8.2.0",
            enabled=True,
            opener=lambda *_args, **_kwargs: LargeResponse({}),
        )

    with pytest.raises(UpdateCheckError, match="response is invalid"):
        check_for_update(
            current_version="8.2.0",
            enabled=True,
            opener=lambda *_args, **_kwargs: _Response(["not", "an", "object"]),
        )


def test_release_check_rejects_non_string_tag_and_invalid_current_version() -> None:
    with pytest.raises(UpdateCheckError, match="release version is invalid"):
        check_for_update(
            current_version="not-a-version",
            enabled=True,
            opener=lambda *_args, **_kwargs: pytest.fail("network must not be opened"),
        )

    with pytest.raises(UpdateCheckError, match="release version is invalid"):
        check_for_update(
            current_version="8.2.0",
            enabled=True,
            opener=lambda *_args, **_kwargs: _Response(
                {"tag_name": 8.3, "draft": False, "prerelease": False}
            ),
        )


def test_invalid_opt_in_setting_fails_closed() -> None:
    loaded = validate_settings({"check_updates_on_startup": "yes"})

    assert loaded.values["check_updates_on_startup"] is False
    assert any("check_updates_on_startup" in warning for warning in loaded.warnings)


def test_version_parser_rejects_non_string_input() -> None:
    with pytest.raises(UpdateCheckError, match="release version is invalid"):
        _parse_version(None)
