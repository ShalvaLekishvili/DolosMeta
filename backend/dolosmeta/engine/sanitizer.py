"""Native, conservative metadata removal for safely rewritable containers."""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path


class SanitizationError(ValueError):
    pass


def _jpeg_without_metadata(data: bytes) -> bytes:
    if not data.startswith(b"\xff\xd8"):
        raise SanitizationError("not a JPEG file")
    output = bytearray(data[:2])
    offset = 2
    while offset < len(data):
        if data[offset] != 0xFF:
            raise SanitizationError("malformed JPEG marker stream")
        marker_start = offset
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            raise SanitizationError("truncated JPEG marker")
        marker = data[offset]
        offset += 1
        if marker == 0xDA:
            output.extend(data[marker_start:])
            break
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            output.extend(data[marker_start:offset])
            continue
        if offset + 2 > len(data):
            raise SanitizationError("truncated JPEG segment")
        segment_length = int.from_bytes(data[offset : offset + 2], "big")
        end = offset + segment_length
        if segment_length < 2 or end > len(data):
            raise SanitizationError("invalid JPEG segment length")
        if not (0xE0 <= marker <= 0xEF or marker == 0xFE):
            output.extend(data[marker_start:end])
        offset = end
    return bytes(output)


def _png_without_metadata(data: bytes) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    if not data.startswith(signature):
        raise SanitizationError("not a PNG file")
    output = bytearray(signature)
    offset = len(signature)
    kept = {b"IHDR", b"PLTE", b"tRNS", b"IDAT", b"IEND"}
    while offset < len(data):
        if offset + 12 > len(data):
            raise SanitizationError("truncated PNG chunk")
        length = int.from_bytes(data[offset : offset + 4], "big")
        end = offset + 12 + length
        if end > len(data):
            raise SanitizationError("invalid PNG chunk length")
        chunk_type = data[offset + 4 : offset + 8]
        if chunk_type in kept:
            output.extend(data[offset:end])
        offset = end
        if chunk_type == b"IEND":
            break
    if not output.endswith(b"IEND\xaeB`\x82"):
        raise SanitizationError("PNG is missing IEND")
    return bytes(output)


def _webp_without_metadata(data: bytes) -> bytes:
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise SanitizationError("not a WebP file")
    chunks = bytearray()
    offset = 12
    while offset + 8 <= len(data):
        chunk_type = data[offset : offset + 4]
        length = int.from_bytes(data[offset + 4 : offset + 8], "little")
        end = offset + 8 + length + (length & 1)
        if end > len(data):
            raise SanitizationError("truncated WebP chunk")
        if chunk_type not in {b"EXIF", b"XMP "}:
            chunks.extend(data[offset:end])
        offset = end
    payload_size = 4 + len(chunks)
    return b"RIFF" + struct.pack("<I", payload_size) + b"WEBP" + bytes(chunks)


def _zip_without_metadata(source: Path, destination: Path) -> None:
    metadata_prefixes = ("docprops/", "customxml/")
    with zipfile.ZipFile(source, "r") as archive, zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED
    ) as cleaned:
        for item in archive.infolist():
            normalized_name = item.filename.lower()
            if normalized_name.startswith(metadata_prefixes):
                continue
            info = zipfile.ZipInfo(item.filename)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0
            info.comment = b""
            info.extra = b""
            cleaned.writestr(info, archive.read(item.filename))


def sanitize_file(source: Path, destination: Path, detected_format: str) -> None:
    file_format = detected_format.upper()
    if file_format in {"JPEG", "JPG"}:
        destination.write_bytes(_jpeg_without_metadata(source.read_bytes()))
        return
    if file_format == "PNG":
        destination.write_bytes(_png_without_metadata(source.read_bytes()))
        return
    if file_format in {"WEBP", "WEBP IMAGE"}:
        destination.write_bytes(_webp_without_metadata(source.read_bytes()))
        return
    if file_format in {"ZIP", "DOCX", "XLSX", "PPTX", "OOXML"}:
        _zip_without_metadata(source, destination)
        return
    raise SanitizationError(
        "This format cannot be safely rewritten by the native cleaner yet."
    )