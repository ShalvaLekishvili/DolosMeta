"""Internal signature-based file detector; extensions are corroborating evidence only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional, Tuple

from dolosmeta.models import DetectionResult


SIGNATURES = (
    (0, b"\xff\xd8\xff", "JPEG", "image/jpeg", ("jpg", "jpeg", "jpe"), "JPEG SOI"),
    (0, b"\x89PNG\r\n\x1a\n", "PNG", "image/png", ("png",), "PNG signature"),
    (0, b"GIF87a", "GIF", "image/gif", ("gif",), "GIF87a"),
    (0, b"GIF89a", "GIF", "image/gif", ("gif",), "GIF89a"),
    (0, b"%PDF-", "PDF", "application/pdf", ("pdf",), "PDF header"),
    (0, b"PK\x03\x04", "ZIP", "application/zip", ("zip", "docx", "xlsx", "pptx", "docm", "xlsm", "pptm"), "ZIP local header"),
    (0, b"PK\x05\x06", "ZIP", "application/zip", ("zip",), "Empty ZIP"),
    (0, b"Rar!\x1a\x07", "RAR", "application/vnd.rar", ("rar",), "RAR signature"),
    (0, b"7z\xbc\xaf\x27\x1c", "7Z", "application/x-7z-compressed", ("7z",), "7-Zip signature"),
    (0, b"\x7fELF", "ELF", "application/x-elf", ("elf", "so", "bin"), "ELF header"),
    (0, b"MZ", "PE", "application/vnd.microsoft.portable-executable", ("exe", "dll", "sys", "scr"), "DOS MZ header"),
    (0, b"\x00\x00\xfe\xff", "Mach-O", "application/x-mach-binary", ("macho", "dylib", "bundle"), "Mach-O 32-bit"),
    (0, b"\xfe\xed\xfa\xce", "Mach-O", "application/x-mach-binary", ("macho", "dylib", "bundle"), "Mach-O 32-bit"),
    (0, b"\xfe\xed\xfa\xcf", "Mach-O", "application/x-mach-binary", ("macho", "dylib", "bundle"), "Mach-O 64-bit"),
    (0, b"\xcf\xfa\xed\xfe", "Mach-O", "application/x-mach-binary", ("macho", "dylib", "bundle"), "Mach-O 64-bit LE"),
    (0, b"\xca\xfe\xba\xbe", "Mach-O Universal", "application/x-mach-binary", ("macho", "dylib"), "Mach-O fat"),
    (0, b"RIFF", "RIFF", "application/octet-stream", ("wav", "webp", "avi"), "RIFF header"),
    (0, b"ID3", "MP3", "audio/mpeg", ("mp3",), "ID3 header"),
    (0, b"fLaC", "FLAC", "audio/flac", ("flac",), "FLAC signature"),
    (0, b"OggS", "OGG", "application/ogg", ("ogg", "oga", "ogv"), "Ogg signature"),
    (0, b"\x1f\x8b\x08", "GZIP", "application/gzip", ("gz", "tgz"), "GZIP header"),
    (0, b"II*\x00", "TIFF", "image/tiff", ("tif", "tiff"), "TIFF little-endian"),
    (0, b"MM\x00*", "TIFF", "image/tiff", ("tif", "tiff"), "TIFF big-endian"),
    (0, b"BM", "BMP", "image/bmp", ("bmp",), "BMP header"),
    (0, b"SQLite format 3\x00", "SQLite", "application/vnd.sqlite3", ("sqlite", "sqlite3", "db"), "SQLite header"),
)


def _mostly_text(data: bytes) -> bool:
    if not data:
        return True
    allowed = sum(1 for byte in data if byte in (9, 10, 13) or 32 <= byte <= 126 or byte >= 0x80)
    if b"\x00" in data:
        return False
    return allowed / len(data) >= 0.90


def _text_detection(data: bytes) -> Tuple[str, str, str, Tuple[str, ...]]:
    stripped = data.lstrip()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return "Text", "text/plain", "Text-like bytes", ("txt", "log", "csv")
    if stripped.startswith((b"{", b"[")):
        try:
            json.loads(text)
            return "JSON", "application/json", "Valid JSON text", ("json",)
        except (ValueError, RecursionError):
            pass
    if stripped.startswith(b"<?xml") or stripped.startswith(b"<svg"):
        return "XML", "application/xml", "XML text", ("xml", "svg")
    first_lines = "\n".join(text.splitlines()[:30]).lower()
    if "from:" in first_lines and ("subject:" in first_lines or "message-id:" in first_lines):
        return "EML", "message/rfc822", "RFC 5322-style headers", ("eml",)
    return "Text", "text/plain", "UTF-8 text", ("txt", "log", "csv", "md")


def detect(header: bytes, size: int, extension: str, tail: bytes = b"") -> DetectionResult:
    ext = extension.lower().lstrip(".")
    for offset, magic, fmt, mime, extensions, label in SIGNATURES:
        if len(header) >= offset + len(magic) and header[offset : offset + len(magic)] == magic:
            if fmt == "RIFF" and len(header) >= 12:
                subtype = header[8:12]
                if subtype == b"WAVE":
                    fmt, mime, extensions, label = "WAV", "audio/wav", ("wav",), "RIFF/WAVE"
                elif subtype == b"WEBP":
                    fmt, mime, extensions, label = "WEBP", "image/webp", ("webp",), "RIFF/WEBP"
                elif subtype == b"AVI ":
                    fmt, mime, extensions, label = "AVI", "video/x-msvideo", ("avi",), "RIFF/AVI"
            return DetectionResult(
                format=fmt,
                mime=mime,
                signature=label,
                confidence=100,
                extensions=list(extensions),
                binary=True,
            )
    if len(header) >= 12 and header[4:8] == b"ftyp":
        brand = header[8:12].decode("latin-1", errors="replace")
        audio_brands = {"M4A ", "M4B ", "M4P "}
        qt = brand == "qt  "
        return DetectionResult(
            format="M4A" if brand in audio_brands else ("MOV" if qt else "MP4"),
            mime="audio/mp4" if brand in audio_brands else ("video/quicktime" if qt else "video/mp4"),
            signature="ISO BMFF ftyp ({})".format(brand.rstrip()),
            confidence=100,
            extensions=["m4a"] if brand in audio_brands else (["mov"] if qt else ["mp4", "m4v"]),
            binary=True,
        )
    if len(header) > 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0:
        return DetectionResult(format="MP3", mime="audio/mpeg", signature="MPEG audio frame", confidence=85, extensions=["mp3"], binary=True)
    if len(header) >= 262 and header[257:262] == b"ustar":
        return DetectionResult(format="TAR", mime="application/x-tar", signature="USTAR header", confidence=100, extensions=["tar"], binary=True)
    sample = header[: min(len(header), 64 * 1024)]
    if _mostly_text(sample):
        fmt, mime, label, extensions = _text_detection(sample)
        return DetectionResult(format=fmt, mime=mime, signature=label, confidence=80, extensions=list(extensions), binary=False)
    return DetectionResult(format="Unknown", mime="application/octet-stream", signature=None, confidence=20, extensions=[], binary=True)


def extension_matches(detection: DetectionResult, extension: str) -> Optional[bool]:
    ext = extension.lower().lstrip(".")
    if not ext or not detection.extensions:
        return None
    return ext in detection.extensions


def extension_of(name: str) -> str:
    suffix = Path(name).suffix.lower()
    return suffix[1:] if suffix.startswith(".") else suffix

