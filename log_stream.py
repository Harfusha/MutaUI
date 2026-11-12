"""Bounded, read-only incremental tailer for explicitly chosen log files."""
from __future__ import annotations

from pathlib import Path


class FileTail:
    def __init__(self, path: str | Path, *, max_chunk: int = 128 * 1024):
        self.path = Path(path)
        self.offset = 0
        self.max_chunk = max(4096, min(int(max_chunk), 1_048_576))
        self._pending = b""
        self._identity = None

    def poll(self) -> list[str]:
        """Read appended lines, detect truncation/replacement, cap read size."""
        st = self.path.stat()
        identity = (st.st_dev, st.st_ino)
        if st.st_size < self.offset or (self._identity is not None and identity != self._identity):
            self.offset = 0
            self._pending = b""
        self._identity = identity
        with self.path.open("rb") as stream:
            if st.st_size - self.offset > self.max_chunk:
                # Follow the newest content if a producer has written a lot.
                self.offset = max(0, st.st_size - self.max_chunk)
                self._pending = b""
            stream.seek(self.offset)
            data = stream.read(self.max_chunk)
            self.offset = stream.tell()
        incoming = self._pending + data
        if b"\n" not in incoming:
            self._pending = incoming[-4096:]
            return []
        *lines, self._pending = incoming.split(b"\n")
        return [line.decode("utf-8", "replace").rstrip("\r") for line in lines]


class TrackedLogLines:
    """Bounded log ring with a monotonic append count for O(new lines) rendering."""

    def __init__(self, maxlen: int = 1200):
        from collections import deque
        if maxlen <= 0:
            raise ValueError('maxlen must be positive')
        self.lines = deque(maxlen=maxlen)
        self.total = 0
        self.epoch = 0

    def append(self, line: str):
        self.lines.append(str(line))
        self.total += 1

    def extend(self, lines):
        for line in lines:
            self.append(line)

    def clear(self):
        self.lines.clear()
        self.total = 0
        self.epoch += 1

    def __iter__(self):
        return iter(self.lines)

    def __len__(self):
        return len(self.lines)

    def since(self, count: int) -> list[str]:
        if count >= self.total:
            return []
        return list(self.lines)[-min(self.total - count, len(self.lines)):]
