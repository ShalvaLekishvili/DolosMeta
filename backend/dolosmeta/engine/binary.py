"""Checked random-access binary reading primitives used by every native parser."""

from __future__ import annotations

import os
import struct
from pathlib import Path
from typing import Optional

from .errors import BoundsError, MalformedFile


class FileSource:
    """Read-only random access to a file without shared seek state."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path).resolve()
        self.size = self.path.stat().st_size
        self._fd = os.open(str(self.path), os.O_RDONLY)

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    def __enter__(self) -> "FileSource":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def read_at(self, offset: int, length: int) -> bytes:
        if offset < 0 or length < 0 or offset > self.size or length > self.size - offset:
            raise BoundsError(
                "read outside file: offset={}, length={}, size={}".format(offset, length, self.size)
            )
        if length == 0:
            return b""
        if hasattr(os, "pread"):
            data = os.pread(self._fd, length, offset)
        else:  # pragma: no cover - Windows fallback
            with self.path.open("rb") as handle:
                handle.seek(offset)
                data = handle.read(length)
        if len(data) != length:
            raise BoundsError("short read at offset {}".format(offset))
        return data


class BinaryReader:
    """A bounded view over a FileSource; all offsets are relative to the view."""

    def __init__(
        self,
        source: FileSource,
        base: int = 0,
        length: Optional[int] = None,
        endian: str = ">",
    ) -> None:
        if base < 0 or base > source.size:
            raise BoundsError("invalid reader base")
        actual_length = source.size - base if length is None else length
        if actual_length < 0 or actual_length > source.size - base:
            raise BoundsError("invalid reader length")
        if endian not in {"<", ">"}:
            raise ValueError("endian must be '<' or '>'")
        self.source = source
        self.base = base
        self.size = actual_length
        self.endian = endian

    def absolute(self, offset: int) -> int:
        self._check(offset, 0)
        return self.base + offset

    def _check(self, offset: int, length: int) -> None:
        if offset < 0 or length < 0 or offset > self.size or length > self.size - offset:
            raise BoundsError(
                "read outside bounded region: offset={}, length={}, size={}".format(
                    offset, length, self.size
                )
            )

    def read(self, offset: int, length: int) -> bytes:
        self._check(offset, length)
        return self.source.read_at(self.base + offset, length)

    def subreader(
        self, offset: int, length: Optional[int] = None, endian: Optional[str] = None
    ) -> "BinaryReader":
        actual = self.size - offset if length is None else length
        self._check(offset, actual)
        return BinaryReader(self.source, self.base + offset, actual, endian or self.endian)

    def unpack(self, fmt: str, offset: int, endian: Optional[str] = None) -> tuple:
        prefix = endian or self.endian
        size = struct.calcsize(prefix + fmt)
        return struct.unpack(prefix + fmt, self.read(offset, size))

    def u8(self, offset: int) -> int:
        return self.read(offset, 1)[0]

    def i8(self, offset: int) -> int:
        return self.unpack("b", offset, ">")[0]

    def u16(self, offset: int, endian: Optional[str] = None) -> int:
        return self.unpack("H", offset, endian)[0]

    def i16(self, offset: int, endian: Optional[str] = None) -> int:
        return self.unpack("h", offset, endian)[0]

    def u24le(self, offset: int) -> int:
        return int.from_bytes(self.read(offset, 3), "little")

    def u32(self, offset: int, endian: Optional[str] = None) -> int:
        return self.unpack("I", offset, endian)[0]

    def i32(self, offset: int, endian: Optional[str] = None) -> int:
        return self.unpack("i", offset, endian)[0]

    def u64(self, offset: int, endian: Optional[str] = None) -> int:
        return self.unpack("Q", offset, endian)[0]

    def i64(self, offset: int, endian: Optional[str] = None) -> int:
        return self.unpack("q", offset, endian)[0]

    def cstring(self, offset: int, maximum: int, encoding: str = "utf-8") -> str:
        if maximum < 0:
            raise BoundsError("negative string maximum")
        raw = self.read(offset, min(maximum, self.size - offset))
        value = raw.split(b"\x00", 1)[0]
        return value.decode(encoding, errors="replace")

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            raise MalformedFile(message)

