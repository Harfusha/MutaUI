from pathlib import Path

import pytest

from log_stream import FileTail


def test_tail_incremental_lines_and_filterable_text(tmp_path: Path):
    file = tmp_path / "daemon.log"
    file.write_bytes(b"hello\nworld\npartial")
    tail = FileTail(file)
    assert tail.poll() == ["hello", "world"]
    assert tail.poll() == []
    with file.open("ab") as out:
        out.write(b" end\nnext\n")
    assert tail.poll() == ["partial end", "next"]


def test_tail_detects_truncation_and_rotation(tmp_path: Path):
    file = tmp_path / "daemon.log"
    file.write_text("something long\n")
    tail = FileTail(file)
    assert tail.poll() == ["something long"]
    file.write_text("x\n")
    assert tail.poll() == ["x"]
    file.rename(tmp_path / "old.log")
    file.write_text("new process\n")
    assert tail.poll() == ["new process"]


def test_tail_bounds_memory_with_large_file(tmp_path: Path):
    file = tmp_path / "large.log"
    file.write_bytes(b"line of data\n" * 10000)
    tail = FileTail(file, max_chunk=4096)
    result = tail.poll()
    assert 0 < len(result) < 10000
    assert tail.poll() == []


def test_tracked_ring_allows_incremental_rendering_through_wrap_and_clear():
    from log_stream import TrackedLogLines

    lines = TrackedLogLines(maxlen=3)
    lines.extend(["a", "b", "c"])
    assert lines.total == 3 and lines.since(0) == ["a", "b", "c"]
    assert lines.since(2) == ["c"]
    lines.extend(["d", "e"])
    assert lines.total == 5
    assert lines.since(3) == ["d", "e"]
    assert list(lines) == ["c", "d", "e"]
    epoch = lines.epoch
    lines.clear()
    assert lines.total == 0 and lines.epoch == epoch + 1
    lines.append("f")
    assert lines.since(0) == ["f"]


def test_tracked_ring_rejects_nonpositive_capacity():
    from log_stream import TrackedLogLines

    with pytest.raises(ValueError, match="maxlen must be positive"):
        TrackedLogLines(maxlen=0)
