"""Format-independent streaming fingerprints, entropy, strings, and hex helpers."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from dolosmeta.config import Settings
from dolosmeta.models import Hashes, Metrics, StringItem


CHUNK_SIZE = 1024 * 1024
ASCII_RE = re.compile(rb"[\x20-\x7e]{4,}")
UTF16LE_RE = re.compile(rb"(?:[\x20-\x7e]\x00){4,}")
UTF16BE_RE = re.compile(rb"(?:\x00[\x20-\x7e]){4,}")
URL_RE = re.compile(r"(?i)^https?://")
EMAIL_RE = re.compile(r"(?i)^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")
IP_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
DOMAIN_RE = re.compile(r"(?i)^(?:[a-z0-9-]+\.)+[a-z]{2,}$")
WINDOWS_PATH_RE = re.compile(r"(?i)^[a-z]:\\")
UNIX_PATH_RE = re.compile(r"^/(?:[^/\x00]+/)*[^/\x00]*$")
REGISTRY_RE = re.compile(r"(?i)^(?:HKEY_|HKLM\\|HKCU\\)")


@dataclass
class StreamStats:
    size: int
    hashes: Hashes
    metrics: Metrics
    header: bytes
    tail: bytes


def entropy_level(value: float) -> str:
    if value < 3.0:
        return "Low"
    if value < 6.0:
        return "Moderate"
    if value < 7.5:
        return "High"
    return "Very High"


def inspect_stream(path: Path, header_limit: int = 64 * 1024, tail_limit: int = 64 * 1024) -> StreamStats:
    algorithms = {
        "md5": hashlib.md5(usedforsecurity=False),
        "sha1": hashlib.sha1(usedforsecurity=False),
        "sha256": hashlib.sha256(),
        "sha512": hashlib.sha512(),
    }
    counts = [0] * 256
    size = 0
    header = bytearray()
    tail = bytearray()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            for digest in algorithms.values():
                digest.update(chunk)
            for byte in chunk:
                counts[byte] += 1
            if len(header) < header_limit:
                header.extend(chunk[: header_limit - len(header)])
            tail.extend(chunk)
            if len(tail) > tail_limit:
                del tail[:-tail_limit]
            size += len(chunk)
    entropy = 0.0
    if size:
        for count in counts:
            if count:
                probability = count / size
                entropy -= probability * math.log2(probability)
    value = round(entropy, 6)
    return StreamStats(
        size=size,
        hashes=Hashes(
            md5=algorithms["md5"].hexdigest(),
            sha1=algorithms["sha1"].hexdigest(),
            sha256=algorithms["sha256"].hexdigest(),
            sha512=algorithms["sha512"].hexdigest(),
        ),
        metrics=Metrics(entropy=value, entropy_level=entropy_level(value)),
        header=bytes(header),
        tail=bytes(tail),
    )


def _category(value: str) -> str:
    stripped = value.strip()
    if URL_RE.search(stripped):
        return "url"
    if EMAIL_RE.search(stripped):
        return "email"
    if IP_RE.search(stripped):
        octets = stripped.split(".")
        if all(int(item) <= 255 for item in octets):
            return "ip_address"
    if REGISTRY_RE.search(stripped):
        return "registry_path"
    if WINDOWS_PATH_RE.search(stripped) or UNIX_PATH_RE.search(stripped):
        return "file_path"
    if DOMAIN_RE.search(stripped):
        return "domain"
    return "generic"


def extract_strings(path: Path, settings: Settings, minimum: int = 4) -> Tuple[List[StringItem], bool]:
    minimum = max(4, min(minimum, 256))
    patterns = (
        (re.compile(rb"[\x20-\x7e]{%d,}" % minimum), "ascii"),
        (re.compile(rb"(?:[\x20-\x7e]\x00){%d,}" % minimum), "utf-16le"),
        (re.compile(rb"(?:\x00[\x20-\x7e]){%d,}" % minimum), "utf-16be"),
    )
    maximum = min(path.stat().st_size, settings.max_string_scan_bytes)
    if maximum == 0:
        return [], False
    # The scan is explicitly capped. A small overlap preserves boundary strings.
    items: List[StringItem] = []
    seen = set()
    overlap = 1024
    consumed = 0
    carry = b""
    with path.open("rb") as handle:
        while consumed < maximum and len(items) < settings.max_strings:
            chunk = handle.read(min(CHUNK_SIZE, maximum - consumed))
            if not chunk:
                break
            data = carry + chunk
            base = consumed - len(carry)
            for pattern, encoding in patterns:
                for match in pattern.finditer(data):
                    absolute = base + match.start()
                    key = (absolute, encoding)
                    if key in seen or absolute < max(0, consumed - len(carry)):
                        continue
                    raw = match.group(0)[:4096]
                    value = raw.decode(encoding, errors="replace")
                    items.append(
                        StringItem(
                            value=value,
                            category=_category(value),
                            encoding=encoding,
                            offset=max(0, absolute),
                        )
                    )
                    seen.add(key)
                    if len(items) >= settings.max_strings:
                        break
                if len(items) >= settings.max_strings:
                    break
            consumed += len(chunk)
            carry = data[-overlap:]
    truncated = maximum < path.stat().st_size or len(items) >= settings.max_strings
    return sorted(items, key=lambda item: (item.offset, item.encoding)), truncated


def hex_view(path: Path, offset: int, length: int, maximum: int) -> Dict[str, object]:
    total = path.stat().st_size
    if offset < 0 or offset > total:
        raise ValueError("hex offset is outside the file")
    requested = max(0, min(length, maximum, total - offset))
    with path.open("rb") as handle:
        handle.seek(offset)
        data = handle.read(requested)
    rows = []
    for index in range(0, len(data), 16):
        chunk = data[index : index + 16]
        rows.append(
            {
                "offset": offset + index,
                "offset_hex": "{:08X}".format(offset + index),
                "hex": " ".join("{:02X}".format(byte) for byte in chunk),
                "ascii": "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in chunk),
            }
        )
    return {
        "offset": offset,
        "length": len(data),
        "total": total,
        "hex": data.hex(),
        "ascii": "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in data),
        "rows": rows,
    }

