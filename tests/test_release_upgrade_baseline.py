"""Version-aware historical release selection for real Windows upgrade tests."""

from __future__ import annotations

import pytest

from scripts.ci.select_upgrade_baseline import parse_stable_tag, select_previous_release

REPO = "Harfusha/MutaUI"


def release(tag: str, installer: bool = True, *, digest: str | None = None):
    name = "MutagenControl-" + tag.lstrip("v") + "-windows-x64-setup.exe"
    asset = {
        "name": name,
        "browser_download_url": f"https://github.com/{REPO}/releases/download/{tag}/{name}",
    }
    if digest is not None:
        asset["digest"] = digest
    return {"tag_name": tag, "assets": [asset] if installer else [], "draft": False, "prerelease": False}


def test_release_baseline_initial_release() -> None:
    assert select_previous_release([], "v8.2.0", REPO) == {"mode": "initial"}


def test_release_baseline_picks_latest_lower_semver_not_api_order() -> None:
    selected = select_previous_release(
        [release("v8.1.0"), release("v8.0.8"), release("v8.1.9")],
        "v8.2.0",
        REPO,
    )
    assert selected["mode"] == "upgrade"
    assert selected["tag"] == "v8.1.9"
    assert selected["sha256"] == ""


def test_release_baseline_requires_prior_real_installer() -> None:
    with pytest.raises(ValueError, match="official Windows installer"):
        select_previous_release([release("v8.1.0", installer=False)], "v8.2.0", REPO)


def test_release_baseline_does_not_publish_downgrade() -> None:
    with pytest.raises(ValueError, match="older"):
        select_previous_release([release("v9.0.0")], "v8.2.0", REPO)


def test_release_baseline_rejects_untrusted_url() -> None:
    prior = release("v8.1.0")
    prior["assets"][0]["browser_download_url"] = "https://example.org/malicious.exe"
    with pytest.raises(ValueError, match="official release asset"):
        select_previous_release([prior], "v8.2.0", REPO)


def test_release_baseline_accepts_and_normalizes_official_digest() -> None:
    prior = release("v8.1.0", digest="sha256:" + "ABCDEF01" * 8)
    selected = select_previous_release([prior], "v8.2.0", REPO)
    assert selected["sha256"] == "abcdef01" * 8


@pytest.mark.parametrize("tag", ["v8.2", "v8.2.0-beta", "v08.2.0", "../8.1.0"])
def test_release_baseline_rejects_nonstable_tags(tag: str) -> None:
    with pytest.raises(ValueError):
        parse_stable_tag(tag)


def test_release_baseline_ignores_drafts_and_prereleases() -> None:
    old = release("v8.1.0")
    old["draft"] = True
    assert select_previous_release([old], "v8.2.0", REPO) == {"mode": "initial"}


def test_release_baseline_rejects_invalid_digest() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        select_previous_release([release("v8.1.0", digest="sha256:bad")], "v8.2.0", REPO)
