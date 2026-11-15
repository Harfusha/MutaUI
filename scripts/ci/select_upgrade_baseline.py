"""Select a real previous release for Windows installer upgrade acceptance.

A missing historical asset is only valid for the actual *first* stable release;
API errors, missing assets on existing releases and invalid source URLs fail shut.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from collections.abc import Sequence
from typing import Any

STABLE_TAG = re.compile(r"^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
INSTALLER_NAME = re.compile(r"^MutagenControl-\d+\.\d+\.\d+-windows-x64-setup\.exe$")


def parse_stable_tag(tag: str) -> tuple[int, int, int]:
    match = STABLE_TAG.fullmatch(tag)
    if match is None:
        raise ValueError("Release tag must be a stable semantic version")
    return tuple(int(part) for part in match.groups())


def select_previous_release(
    releases: Sequence[dict[str, Any]],
    current_tag: str,
    repository: str,
) -> dict[str, str]:
    """Select the highest prior stable release; validate genuine installer metadata."""
    current_version = parse_stable_tag(current_tag)
    if REPOSITORY.fullmatch(repository) is None:
        raise ValueError("Invalid GitHub repository identifier")

    older: list[tuple[tuple[int, int, int], dict[str, Any]]] = []
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        tag = release.get("tag_name")
        if not isinstance(tag, str):
            continue
        try:
            release_version = parse_stable_tag(tag)
        except ValueError:
            continue
        if release_version > current_version:
            raise ValueError("Refusing to publish a release older than an existing stable release")
        if release_version < current_version:
            older.append((release_version, release))

    if not older:
        return {"mode": "initial"}

    _, previous = max(older, key=lambda item: item[0])
    tag = previous["tag_name"]
    assets = previous.get("assets") or []
    installers = [
        asset
        for asset in assets
        if isinstance(asset, dict)
        and isinstance(asset.get("name"), str)
        and INSTALLER_NAME.fullmatch(asset["name"]) is not None
        and asset["name"].startswith(
            "MutagenControl-" + ".".join(str(n) for n in parse_stable_tag(tag))
        )
    ]
    if len(installers) != 1:
        raise ValueError("Previous stable release lacks exactly one official Windows installer")
    asset = installers[0]
    url = asset.get("browser_download_url")
    prefix = f"https://github.com/{repository}/releases/download/{tag}/"
    if not isinstance(url, str) or url != prefix + asset["name"]:
        raise ValueError("Previous installer URL is not the official release asset")

    raw_digest = asset.get("digest")
    digest = ""
    if raw_digest is not None:
        if (
            not isinstance(raw_digest, str)
            or re.fullmatch(r"sha256:[0-9a-fA-F]{64}", raw_digest) is None
        ):
            raise ValueError("Previous installer has an invalid SHA-256 digest")
        digest = raw_digest.split(":", 1)[1].lower()

    return {"mode": "upgrade", "tag": tag, "url": url, "sha256": digest}


def fetch_releases(repository: str, *, token: str = "") -> list[dict[str, Any]]:
    if REPOSITORY.fullmatch(repository) is None:
        raise ValueError("Invalid GitHub repository identifier")
    releases: list[dict[str, Any]] = []
    for page in range(1, 11):
        url = f"https://api.github.com/repos/{repository}/releases?per_page=100&page={page}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "MutaUI-release-upgrade-verification",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            batch = json.load(response)
        if not isinstance(batch, list) or any(not isinstance(item, dict) for item in batch):
            raise ValueError("Invalid GitHub releases API response")
        releases.extend(batch)
        if len(batch) < 100:
            return releases
    raise ValueError("Too many releases for verified upgrade history; refusing unsafe fallback")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--current-tag", required=True)
    args = parser.parse_args(argv)
    try:
        releases = fetch_releases(args.repo, token=os.environ.get("GITHUB_TOKEN", ""))
        selection = select_previous_release(releases, args.current_tag, args.repo)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(
            f"Cannot establish prior release provenance: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(selection, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
