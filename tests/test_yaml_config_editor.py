import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import mutaui.adapters.yaml_config_editor as yaml_editor
from mutaui.adapters.yaml_config import load_yaml_file
from mutaui.adapters.yaml_config_editor import (
    ConcurrentConfigChange,
    InvalidConfigForWrite,
    apply_yaml_edit,
    preview_yaml_edit,
    preview_yaml_text,
)


def test_preview_is_diff_only_and_keeps_yaml_provenance(tmp_path):
    path = tmp_path / "mutagen.yml"
    original = b"# keep me\nsync:\n  defaults:\n    watch: true\nfuture: [x, y]\n"
    path.write_bytes(original)
    snapshot = load_yaml_file(path)

    preview = preview_yaml_edit(
        snapshot, {"sync": {"defaults": {"watch": False}}, "future": ["x", "y"]}
    )

    assert "# keep me" in preview.yaml_text
    assert "future:" in preview.yaml_text
    assert "-    watch: true" in preview.diff
    assert "+    watch: false" in preview.diff
    assert path.read_bytes() == original


def test_preview_preserves_utf8_bom_and_crlf(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_bytes(b"\xef\xbb\xbf" + b"sync:\r\n  defaults:\r\n    watch: true\r\n")
    preview = preview_yaml_edit(load_yaml_file(path), {"sync": {"defaults": {"watch": False}}})
    assert preview.yaml_bytes.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in preview.yaml_bytes
    assert b"\n" not in preview.yaml_bytes.replace(b"\r\n", b"")


def test_preview_text_restores_missing_source_bom(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_bytes(b"\xef\xbb\xbf" + b"sync:\n  defaults: {}\n")
    preview = preview_yaml_text(load_yaml_file(path), "sync:\n  defaults: {}\n")
    assert preview.yaml_bytes.startswith(b"\xef\xbb\xbf")


def test_preview_preserves_carriage_return_only_newlines(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_bytes(b"sync:\r  defaults: {}\r")
    preview = preview_yaml_edit(load_yaml_file(path), {"sync": {"defaults": {"watch": True}}})
    assert b"\r" in preview.yaml_bytes
    assert b"\n" not in preview.yaml_bytes


def test_preview_refuses_directory_as_source_path(tmp_path):
    source = tmp_path / "mutagen.yml"
    source.write_text("sync: {}\n", encoding="utf-8")
    snapshot = load_yaml_file(source)
    directory = tmp_path / "config-dir"
    directory.mkdir()
    forged_path_snapshot = replace(snapshot, source_path=str(directory))
    with pytest.raises(InvalidConfigForWrite, match="regular, non-symlink"):
        preview_yaml_edit(forged_path_snapshot, {})


def test_apply_makes_backup_atomically_and_preserves_mode(tmp_path):
    path = tmp_path / "mutagen.yml"
    original = b"sync:\n  defaults:\n    watch: true\n"
    path.write_bytes(original)
    os.chmod(path, 0o640)
    snapshot = load_yaml_file(path)
    preview = preview_yaml_edit(snapshot, {"sync": {"defaults": {"watch": False}}})

    result = apply_yaml_edit(preview, backup_suffix=".bak")

    assert path.read_bytes() == preview.yaml_bytes
    assert (tmp_path / "mutagen.yml.bak").read_bytes() == original
    if os.name != "nt":
        assert os.stat(path).st_mode & 0o777 == 0o640
    assert result.sha256 == snapshot.sha256
    assert result.new_sha256 != snapshot.sha256


def test_posix_atomic_replace_path_is_exercised_on_any_host(tmp_path, monkeypatch):
    path = tmp_path / "mutagen.yml"
    original = b"sync:\n  defaults:\n    watch: true\n"
    path.write_bytes(original)
    preview = preview_yaml_edit(load_yaml_file(path), {"sync": {"defaults": {"watch": False}}})
    preview = replace(preview, provenance=replace(preview.provenance, mode=None))
    monkeypatch.setattr(
        yaml_editor,
        "os",
        SimpleNamespace(
            name="posix",
            fdopen=os.fdopen,
            fsync=os.fsync,
            chmod=os.chmod,
            replace=os.replace,
        ),
    )
    monkeypatch.setattr(yaml_editor, "_flush_directory", lambda _directory: None)

    result = apply_yaml_edit(preview, backup_suffix=".posix-test.bak")

    assert result.backup_path.read_bytes() == original
    assert path.read_bytes() == preview.yaml_bytes


def test_posix_directory_flush_closes_descriptor(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        yaml_editor,
        "os",
        SimpleNamespace(
            name="posix",
            O_RDONLY=7,
            open=lambda path, flags: calls.append(("open", path, flags)) or 42,
            fsync=lambda descriptor: calls.append(("fsync", descriptor)),
            close=lambda descriptor: calls.append(("close", descriptor)),
        ),
    )

    yaml_editor._flush_directory(tmp_path)

    assert calls == [
        ("open", tmp_path, 7),
        ("fsync", 42),
        ("close", 42),
    ]


def test_windows_atomic_replace_failure_raises_os_error(tmp_path, monkeypatch):
    import ctypes

    class ReplaceFile:
        argtypes = None
        restype = None

        def __call__(self, *_args):
            return 0

    class Kernel32:
        ReplaceFileW = ReplaceFile()

    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: Kernel32(), raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 5, raising=False)
    monkeypatch.setattr(
        ctypes, "WinError", lambda code: OSError(code, "access denied"), raising=False
    )

    with pytest.raises(OSError, match="access denied"):
        yaml_editor._replace_windows(
            tmp_path / "mutagen.yml",
            tmp_path / "mutagen.yml.tmp",
            tmp_path / "mutagen.yml.bak",
        )


def test_apply_rejects_symlink_race_after_temp_write(tmp_path, monkeypatch):
    path = tmp_path / "mutagen.yml"
    path.write_bytes(b"sync:\n  defaults:\n    watch: true\n")
    snapshot = load_yaml_file(path)
    preview = preview_yaml_edit(snapshot, {"sync": {"defaults": {"watch": False}}})
    monkeypatch.setattr(yaml_editor, "load_yaml_file", lambda _path: snapshot)
    original_is_symlink = Path.is_symlink
    checks = 0

    def symlink_race(candidate):
        nonlocal checks
        if candidate == path:
            checks += 1
            return checks >= 2
        return original_is_symlink(candidate)

    monkeypatch.setattr(Path, "is_symlink", symlink_race)

    with pytest.raises(InvalidConfigForWrite, match="became a symlink"):
        apply_yaml_edit(preview)
    assert path.read_bytes() == snapshot.raw_bytes


def test_external_change_rejects_write_and_returns_reload_merge_cancel_options(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text("sync: {}\n", encoding="utf-8")
    snapshot = load_yaml_file(path)
    preview = preview_yaml_edit(snapshot, {"sync": {"defaults": {"watch": True}}})
    external = b"sync:\n  defaults:\n    watch: false\n"
    path.write_bytes(external)

    with pytest.raises(ConcurrentConfigChange) as exc_info:
        apply_yaml_edit(preview)

    assert exc_info.value.latest.raw_bytes == external
    assert exc_info.value.options == ("reload", "merge", "cancel")
    assert path.read_bytes() == external


def test_invalid_source_cannot_be_previewed_or_written(tmp_path):
    path = tmp_path / "mutagen.yml"
    source = b"sync: [broken\n"
    path.write_bytes(source)
    snapshot = load_yaml_file(path)

    with pytest.raises(InvalidConfigForWrite):
        preview_yaml_edit(snapshot, {})

    assert path.read_bytes() == source


def test_preview_rejects_invalid_replacement_without_touching_source(tmp_path):
    path = tmp_path / "mutagen.yml"
    original = b"sync: {}\n"
    path.write_bytes(original)
    snapshot = load_yaml_file(path)

    with pytest.raises(InvalidConfigForWrite):
        preview_yaml_edit(snapshot, {"sync": [object()]})

    assert path.read_bytes() == original


def test_text_preview_rejects_non_text_and_invalid_yaml(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_bytes(b"sync: {}\n")
    snapshot = load_yaml_file(path)

    with pytest.raises(InvalidConfigForWrite, match="must be text"):
        preview_yaml_text(snapshot, None)
    with pytest.raises(InvalidConfigForWrite, match="failed validation"):
        preview_yaml_text(snapshot, "sync: [broken\n")


def test_yaml_edit_rejects_non_mapping_changes_and_non_string_keys(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text("sync: {}\n", encoding="utf-8")
    snapshot = load_yaml_file(path)

    with pytest.raises(InvalidConfigForWrite, match="must be a mapping"):
        preview_yaml_edit(snapshot, [])
    with pytest.raises(InvalidConfigForWrite, match="keys must be strings"):
        preview_yaml_edit(snapshot, {1: "invalid"})


def test_yaml_edit_rejects_snapshot_after_source_removal(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text("sync: {}\n", encoding="utf-8")
    snapshot = load_yaml_file(path)
    path.unlink()

    with pytest.raises(InvalidConfigForWrite, match="Could not inspect"):
        preview_yaml_edit(snapshot, {"sync": {}})


def test_mapping_preview_wraps_serializer_failure(tmp_path, monkeypatch):
    path = tmp_path / "mutagen.yml"
    path.write_text("sync: {}\n", encoding="utf-8")
    snapshot = load_yaml_file(path)
    monkeypatch.setattr(
        yaml_editor,
        "render_yaml_preview",
        lambda _document: (_ for _ in ()).throw(ValueError("boom")),
    )

    with pytest.raises(InvalidConfigForWrite, match="cannot be serialized"):
        preview_yaml_edit(snapshot, {"sync": {"defaults": {"watch": True}}})


def test_apply_rejects_symlink_before_writing(tmp_path, monkeypatch):
    path = tmp_path / "mutagen.yml"
    path.write_text("sync: {}\n", encoding="utf-8")
    snapshot = load_yaml_file(path)
    preview = preview_yaml_edit(snapshot, {"sync": {"defaults": {"watch": True}}})
    original_is_symlink = type(path).is_symlink

    def is_target_symlink(candidate):
        if candidate == path:
            return True
        return original_is_symlink(candidate)

    monkeypatch.setattr(type(path), "is_symlink", is_target_symlink)
    with pytest.raises(InvalidConfigForWrite, match="became a symlink"):
        apply_yaml_edit(preview)
    assert path.read_text(encoding="utf-8") == "sync: {}\n"


def test_apply_rechecks_source_after_initial_validation(tmp_path, monkeypatch):
    path = tmp_path / "mutagen.yml"
    original = b"sync: {}\n"
    path.write_bytes(original)
    preview = preview_yaml_edit(load_yaml_file(path), {"sync": {"defaults": {"watch": True}}})

    def change_source_then_choose_backup(source, suffix):
        source.write_bytes(b"sync:\n  defaults:\n    watch: false\n")
        return source.with_name(source.name + (suffix or ".bak"))

    monkeypatch.setattr(yaml_editor, "_backup_name", change_source_then_choose_backup)
    with pytest.raises(ConcurrentConfigChange):
        apply_yaml_edit(preview)
    assert b"watch: false" in path.read_bytes()


def test_apply_refuses_existing_fixed_backup(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text("sync: {}\n", encoding="utf-8")
    backup = tmp_path / "mutagen.yml.bak"
    backup.write_text("preserve me", encoding="utf-8")
    preview = preview_yaml_edit(load_yaml_file(path), {"sync": {"defaults": {"watch": True}}})

    with pytest.raises(FileExistsError, match="Backup already exists"):
        apply_yaml_edit(preview, backup_suffix=".bak")

    assert backup.read_text(encoding="utf-8") == "preserve me"
    assert path.read_text(encoding="utf-8") == "sync: {}\n"


def test_timestamp_backup_selects_next_free_name(tmp_path, monkeypatch):
    path = tmp_path / "mutagen.yml"
    path.write_text("sync: {}\n", encoding="utf-8")
    (tmp_path / "mutagen.yml.fixed.bak").write_text("keep", encoding="utf-8")

    class FixedDateTime:
        @staticmethod
        def now(_timezone):
            class Moment:
                @staticmethod
                def strftime(_format):
                    return "fixed"

            return Moment()

    monkeypatch.setattr(yaml_editor, "datetime", FixedDateTime)

    assert yaml_editor._backup_name(path, None).name == "mutagen.yml.fixed.1.bak"
