"""Bounded, non-rendering PDF metadata and active-content inspector."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

from ..binary import BinaryReader
from .base import OutputBuilder, ParseContext, ParserDescriptor, ParserOutput, safe_text
from .xmlmeta import parse_xmp_bytes


OBJECT_RE = re.compile(rb"(?<!\d)(\d{1,10})\s+(\d{1,10})\s+obj\b")
PAGE_RE = re.compile(rb"/Type\s*/Page(?!s)\b")
FONT_RE = re.compile(rb"/Type\s*/Font\b")
IMAGE_RE = re.compile(rb"/Subtype\s*/Image\b")


def _literal_after(data: bytes, marker: bytes) -> Optional[str]:
    position = data.find(marker)
    if position < 0:
        return None
    position += len(marker)
    while position < len(data) and data[position] in b" \t\r\n":
        position += 1
    if position >= len(data):
        return None
    if data[position] == 0x28:
        position += 1
        depth = 1
        escaped = False
        output = bytearray()
        while position < len(data) and len(output) < 65_536:
            byte = data[position]
            position += 1
            if escaped:
                replacements = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}
                output.append(replacements.get(byte, byte))
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x28:
                depth += 1
                output.append(byte)
            elif byte == 0x29:
                depth -= 1
                if depth == 0:
                    return safe_text(bytes(output), "utf-8", 65_536)
                output.append(byte)
            else:
                output.append(byte)
    elif data[position] == 0x3C and position + 1 < len(data) and data[position + 1] != 0x3C:
        end = data.find(b">", position + 1, min(len(data), position + 131_072))
        if end > position:
            raw = re.sub(rb"\s+", b"", data[position + 1 : end])
            try:
                decoded = bytes.fromhex(raw.decode("ascii"))
                if decoded.startswith((b"\xfe\xff", b"\xff\xfe")):
                    return decoded[2:].decode("utf-16-be" if decoded[:2] == b"\xfe\xff" else "utf-16-le", errors="replace")
                return safe_text(decoded, "utf-8", 65_536)
            except (ValueError, UnicodeError):
                return None
    return None


class PDFParser:
    descriptor = ParserDescriptor(
        name="PDF Parser",
        version="1.0",
        formats=("PDF",),
        capability="good",
        description="Static PDF header, direct metadata, structure counts, XMP, and active-content indicators",
    )

    def parse(self, reader: BinaryReader, context: ParseContext) -> ParserOutput:
        builder = OutputBuilder("pdf", context.budget)
        root_id = builder.node("PDF", "document", reader.base, reader.size)
        maximum = context.budget.settings.max_metadata_block_bytes
        segment_size = min(reader.size, max(4096, maximum // 2))
        segments: List[Tuple[int, bytes]] = [(0, reader.read(0, segment_size))]
        if reader.size > segment_size:
            tail_start = max(segment_size, reader.size - segment_size)
            segments.append((tail_start, reader.read(tail_start, reader.size - tail_start)))
            context.budget.note("PDF structural scan bounded to head and tail metadata windows")
        head = segments[0][1]
        if not head.startswith(b"%PDF-"):
            builder.warn("pdf.signature", "PDF header is missing", reader.base)
            return builder.output
        version = safe_text(head[5:12].splitlines()[0], "ascii", 16)
        builder.record("PDF", "Version", "PDF.Version", version, "document", offset=reader.base, length=min(12, reader.size))
        combined = b"\n".join(data for _, data in segments)
        builder.record("PDF", "Linearized", "PDF.Linearized", b"/Linearized" in head[:4096], "document")
        object_ids: Set[Tuple[bytes, bytes]] = set()
        for base, data in segments:
            for match in OBJECT_RE.finditer(data):
                object_ids.add((match.group(1), match.group(2)))
                if len(object_ids) >= context.budget.settings.max_structure_nodes:
                    break
        pages = sum(len(PAGE_RE.findall(data)) for _, data in segments)
        fonts = sum(len(FONT_RE.findall(data)) for _, data in segments)
        images = sum(len(IMAGE_RE.findall(data)) for _, data in segments)
        for name, value in (
            ("ObjectCountObserved", len(object_ids)),
            ("PageCountObserved", pages),
            ("FontObjectCountObserved", fonts),
            ("ImageObjectCountObserved", images),
            ("Encrypted", b"/Encrypt" in combined),
            ("MetadataStreamPresent", b"/Type /Metadata" in combined or b"/Type/Metadata" in combined),
            ("AcroFormPresent", b"/AcroForm" in combined),
            ("EmbeddedFilesPresent", b"/EmbeddedFiles" in combined or b"/Type /Filespec" in combined),
        ):
            builder.record("PDF", name, "PDF.{}".format(name), value, "security" if name.endswith("Present") or name == "Encrypted" else "document")
        for key in ("Title", "Author", "Subject", "Keywords", "Creator", "Producer", "CreationDate", "ModDate", "Trapped"):
            value = None
            for _, data in segments:
                value = _literal_after(data, ("/" + key).encode("ascii"))
                if value is not None:
                    break
            if value is not None:
                category = "time" if key in {"CreationDate", "ModDate"} else ("author" if key == "Author" else ("software" if key in {"Creator", "Producer"} else "document"))
                builder.record("PDF.Info", key, "PDF.Info.{}".format(key), value, category)
        indicators = (
            (b"/JavaScript", "JavaScript", "pdf.javascript", 18),
            (b"/JS", "JavaScriptAction", "pdf.javascript_action", 18),
            (b"/Launch", "LaunchAction", "pdf.launch_action", 25),
            (b"/OpenAction", "OpenAction", "pdf.open_action", 10),
            (b"/AA", "AdditionalActions", "pdf.additional_actions", 10),
            (b"/EmbeddedFiles", "EmbeddedFiles", "pdf.embedded_files", 12),
            (b"/RichMedia", "RichMedia", "pdf.rich_media", 15),
        )
        for token, name, _code, points in indicators:
            if token in combined:
                builder.record("PDF.Security", name, "PDF.Security.{}".format(name), True, "security", description="Static indicator only; DolosMeta did not execute PDF content")
        for base, data in segments:
            start = data.find(b"<x:xmpmeta")
            if start < 0:
                start = data.find(b"<xmpmeta")
            if start >= 0:
                end_tag = b"</x:xmpmeta>" if data[start : start + 20].startswith(b"<x:xmpmeta") else b"</xmpmeta>"
                end = data.find(end_tag, start)
                if end >= 0:
                    end += len(end_tag)
                    builder.output.extend(parse_xmp_bytes(data[start:end], context, reader.base + base + start))
                    break
        builder.node("Observed objects", "object-index", reader.base, reader.size, root_id, {"count": len(object_ids), "scan_bounded": reader.size > maximum})
        if b"/ObjStm" in combined:
            builder.warn("pdf.object_streams", "Compressed object streams are present; counts and direct Info fields may be incomplete")
        if b"/Encrypt" in combined:
            builder.warn("pdf.encrypted", "The PDF is encrypted; recoverable metadata may be incomplete")
        return builder.output

