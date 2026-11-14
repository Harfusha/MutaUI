from pathlib import Path

import pytest

import mutaui.services.diff_integration as diff_integration
from mutaui.services.diff_integration import (
    DiffIntegrationError,
    copy_local_conflict_for_diff,
    external_diff_arguments,
)


def test_diff_copy_is_bounded_contained_and_read_only(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "nested").mkdir()
    source = root / "nested" / "file.txt"
    source.write_bytes(b"local side")
    temp = tmp_path / "private"
    temp.mkdir()

    copy = copy_local_conflict_for_diff(str(root), "nested/file.txt", destination_directory=temp)

    assert copy.path.read_bytes() == b"local side"
    assert copy.size_bytes == 10
    assert len(copy.sha256) == 64
    assert source.read_bytes() == b"local side"

    with pytest.raises(DiffIntegrationError, match="missing or outside"):
        copy_local_conflict_for_diff(str(root), "../outside", destination_directory=temp)
    with pytest.raises(DiffIntegrationError, match="size limit"):
        copy_local_conflict_for_diff(
            str(root), "nested/file.txt", destination_directory=temp, max_bytes=2
        )


def test_external_diff_uses_exact_argument_vector_without_shell(tmp_path):
    executable = tmp_path / "Meld.exe"
    executable.write_bytes(b"binary placeholder")
    left = tmp_path / "left copy.txt"
    right = tmp_path / "right copy.txt"
    left.write_text("left", encoding="utf-8")
    right.write_text("right", encoding="utf-8")
    arguments = external_diff_arguments(executable, left, right)

    assert arguments == (str(executable.absolute()), str(left.absolute()), str(right.absolute()))


def test_external_diff_refuses_missing_or_symlinked_inputs(tmp_path):
    executable = tmp_path / "diff.exe"
    executable.write_text("x", encoding="utf-8")
    left = tmp_path / "left"
    left.write_text("left", encoding="utf-8")
    with pytest.raises(DiffIntegrationError, match="existing regular local copies"):
        external_diff_arguments(executable, left, tmp_path / "missing")
    with pytest.raises(DiffIntegrationError, match="regular diff-tool executable"):
        external_diff_arguments(tmp_path / "missing-tool", left, left)


def test_failed_copy_does_not_delete_a_preexisting_destination_file(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    source = root / "file.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "private"
    destination.mkdir()
    protected = destination / "local-conflict-copy"
    protected.write_text("existing operator file", encoding="utf-8")

    with pytest.raises(FileExistsError):
        copy_local_conflict_for_diff(str(root), "file.txt", destination_directory=destination)

    assert protected.read_text(encoding="utf-8") == "existing operator file"


def test_copy_removes_its_partial_output_when_durable_write_fails(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    source = root / "file.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "private"
    destination.mkdir()
    monkeypatch.setattr(
        diff_integration.os,
        "fsync",
        lambda _descriptor: (_ for _ in ()).throw(OSError("disk full")),
    )

    with pytest.raises(OSError, match="disk full"):
        diff_integration.copy_local_conflict_for_diff(
            str(root), "file.txt", destination_directory=destination
        )

    assert not (destination / "local-conflict-copy").exists()


def test_diff_copy_rejects_non_directory_and_oversized_source(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    source = root / "file.txt"
    source.write_text("large", encoding="utf-8")
    destination_file = tmp_path / "not-a-directory"
    destination_file.write_text("x", encoding="utf-8")

    with pytest.raises(DiffIntegrationError, match="existing private temporary directory"):
        diff_integration.copy_local_conflict_for_diff(
            str(root), "file.txt", destination_directory=destination_file
        )

    destination = tmp_path / "private"
    destination.mkdir()
    with pytest.raises(DiffIntegrationError, match="within the size limit"):
        diff_integration.copy_local_conflict_for_diff(
            str(root), "file.txt", destination_directory=destination, max_bytes=2
        )
    assert not (destination / "local-conflict-copy").exists()


@pytest.mark.parametrize("race", ["growth", "changed-after-copy"])
def test_diff_copy_rejects_source_mutation_during_copy(tmp_path, monkeypatch, race):
    root = tmp_path / "root"
    root.mkdir()
    source = root / "file.txt"
    source.write_bytes(b"x")
    destination = tmp_path / f"private-{race}"
    destination.mkdir()
    original_open = Path.open

    if race == "growth":

        def racing_open(candidate, mode="r", *args, **kwargs):
            if candidate == source and mode == "rb":
                with original_open(candidate, "ab") as stream:
                    stream.write(b"grew")
            return original_open(candidate, mode, *args, **kwargs)

        monkeypatch.setattr(Path, "open", racing_open)
        expected = "exceeded the size limit"
        limit = 1
    else:

        class MutatingReader:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                self.stream.__enter__()
                return self

            def read(self, count):
                return self.stream.read(count)

            def __exit__(self, *args):
                result = self.stream.__exit__(*args)
                source.write_bytes(b"changed after the copy")
                return result

        def racing_open(candidate, mode="r", *args, **kwargs):
            stream = original_open(candidate, mode, *args, **kwargs)
            if candidate == source and mode == "rb":
                return MutatingReader(stream)
            return stream

        monkeypatch.setattr(Path, "open", racing_open)
        expected = "changed while its diff copy was made"
        limit = 10

    with pytest.raises(DiffIntegrationError, match=expected):
        copy_local_conflict_for_diff(
            str(root), "file.txt", destination_directory=destination, max_bytes=limit
        )
    assert not (destination / "local-conflict-copy").exists()
