"""Read-only, bounded round-trip parser for native Mutagen YAML configuration."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.error import YAMLError

YAML_MAX_BYTES = 4 * 1024 * 1024
_MAX_INDENT = 128


@dataclass(frozen=True, slots=True)
class YAMLReadResult:
    raw_bytes: bytes
    text: str | None
    document: CommentedMap | None
    sha256: str
    encoding: str | None
    newline: str | None
    source_path: str | None = None
    error: str = ""

    @property
    def valid(self) -> bool:
        return not self.error and self.document is not None


def _newline_style(raw_bytes: bytes) -> str | None:
    if b"\r\n" in raw_bytes:
        return "\r\n"
    if b"\n" in raw_bytes:
        return "\n"
    if b"\r" in raw_bytes:
        return "\r"
    return None


def _error_result(
    raw_bytes: bytes,
    error: str,
    *,
    source_path: str | None = None,
    text: str | None = None,
    encoding: str | None = None,
) -> YAMLReadResult:
    return YAMLReadResult(
        raw_bytes=raw_bytes,
        text=text,
        document=None,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        encoding=encoding,
        newline=_newline_style(raw_bytes),
        source_path=source_path,
        error=error,
    )


def _parser() -> YAML:
    parser = YAML(typ="rt")
    parser.preserve_quotes = True
    parser.allow_duplicate_keys = False
    parser.width = 4096
    # ruamel.yaml 0.19 added this resource guard. Keep the check compatible with
    # the tested 0.18 series, where the byte and indentation limits still apply.
    if hasattr(parser, "max_depth"):
        parser.max_depth = 64
    return parser


def parse_yaml_bytes(raw_bytes: bytes, *, source_path: str | None = None) -> YAMLReadResult:
    if not isinstance(raw_bytes, bytes):
        raise TypeError("YAML source must be bytes.")
    digest = hashlib.sha256(raw_bytes).hexdigest()
    if len(raw_bytes) > YAML_MAX_BYTES:
        return _error_result(
            raw_bytes,
            f"YAML source exceeds the {YAML_MAX_BYTES}-byte size limit.",
            source_path=source_path,
        )

    encoding = "utf-8-sig" if raw_bytes.startswith(b"\xef\xbb\xbf") else "utf-8"
    try:
        text = raw_bytes.decode(encoding)
    except UnicodeDecodeError:
        return _error_result(
            raw_bytes,
            "YAML source is not valid UTF-8; original bytes were retained.",
            source_path=source_path,
            encoding=encoding,
        )

    if any(len(line) - len(line.lstrip(" ")) > _MAX_INDENT for line in text.splitlines()):
        return _error_result(
            raw_bytes,
            f"YAML indentation exceeds the {_MAX_INDENT}-space limit.",
            source_path=source_path,
            text=text,
            encoding=encoding,
        )

    try:
        document = _parser().load(text)
    except (YAMLError, RecursionError, ValueError) as exc:
        return _error_result(
            raw_bytes,
            f"YAML parse failed: {type(exc).__name__}.",
            source_path=source_path,
            text=text,
            encoding=encoding,
        )

    if document is None:
        document = CommentedMap()
    if not isinstance(document, CommentedMap):
        return _error_result(
            raw_bytes,
            "Mutagen YAML root must be a mapping; original bytes were retained.",
            source_path=source_path,
            text=text,
            encoding=encoding,
        )
    return YAMLReadResult(
        raw_bytes=raw_bytes,
        text=text,
        document=document,
        sha256=digest,
        encoding=encoding,
        newline=_newline_style(raw_bytes),
        source_path=source_path,
    )


def load_yaml_file(path: str | Path) -> YAMLReadResult:
    source_path = str(path)
    try:
        raw_bytes = Path(path).read_bytes()
    except OSError as exc:
        return _error_result(
            b"",
            f"Could not read YAML source: {exc.strerror or type(exc).__name__}.",
            source_path=source_path,
        )
    return parse_yaml_bytes(raw_bytes, source_path=source_path)


def render_yaml_preview(document: Any) -> str:
    """Serialize an in-memory preview only; this module never writes config files."""
    stream = io.StringIO()
    _parser().dump(document, stream)
    return stream.getvalue()
