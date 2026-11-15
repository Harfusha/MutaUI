#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-${RUNNER_TEMP:-/tmp}/actionlint}"
python "${SCRIPT_DIR}/install_actionlint.py" "$TARGET_DIR"
