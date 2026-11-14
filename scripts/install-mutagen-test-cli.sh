#!/usr/bin/env bash
set -euo pipefail

VERSION="${MUTAGEN_TEST_VERSION:-0.18.1}"
ROOT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/mutagen-test-cli"
mkdir -p "$ROOT"

case "$(uname -s)" in
  Darwin) PLATFORM=darwin ;;
  Linux) PLATFORM=linux ;;
  *) echo "Unsupported Mutagen test host: $(uname -s)" >&2; exit 2 ;;
esac
case "$(uname -m)" in
  x86_64|amd64) ARCH=amd64 ;;
  arm64|aarch64) ARCH=arm64 ;;
  *) echo "Unsupported Mutagen test architecture: $(uname -m)" >&2; exit 2 ;;
esac

ARCHIVE="$ROOT/mutagen_${PLATFORM}_${ARCH}_v${VERSION}.tar.gz"
ARCHIVE_NAME="mutagen_${PLATFORM}_${ARCH}_v${VERSION}.tar.gz"
RELEASE_URL="https://github.com/mutagen-io/mutagen/releases/download/v${VERSION}"
URL="$RELEASE_URL/$ARCHIVE_NAME"
CHECKSUMS="$ROOT/SHA256SUMS"
curl --fail --location --retry 3 --proto '=https' --tlsv1.2 --output "$ARCHIVE" "$URL"
curl --fail --location --retry 3 --proto '=https' --tlsv1.2 --output "$CHECKSUMS" "$RELEASE_URL/SHA256SUMS"
EXPECTED_HASH="$(awk -v name="$ARCHIVE_NAME" '$2 == name { print $1 }' "$CHECKSUMS")"
if [[ ! "$EXPECTED_HASH" =~ ^[[:xdigit:]]{64}$ ]]; then
  echo "Missing or invalid SHA-256 for $ARCHIVE_NAME in the official release manifest." >&2
  exit 1
fi
ACTUAL_HASH="$(shasum -a 256 "$ARCHIVE" | awk '{print $1}')"
if [[ "$ACTUAL_HASH" != "$EXPECTED_HASH" ]]; then
  echo "SHA-256 verification failed for $ARCHIVE_NAME." >&2
  exit 1
fi
tar -xzf "$ARCHIVE" -C "$ROOT"
MUTAGEN_BINARY="$(find "$ROOT" -type f -name mutagen -perm -u+x -print -quit)"
if [[ -z "$MUTAGEN_BINARY" ]]; then echo 'Mutagen executable was missing from the official archive.' >&2; exit 1; fi
"$MUTAGEN_BINARY" version
if [[ -n "${GITHUB_ENV:-}" ]]; then printf 'MUTAGEN_BINARY=%s\n' "$MUTAGEN_BINARY" >> "$GITHUB_ENV"; fi
