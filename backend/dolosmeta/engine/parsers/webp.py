"""Native RIFF/WebP structural and metadata parser."""

from __future__ import annotations

from ..binary import BinaryReader
from ..errors import BoundsError, LimitExceeded
from .base import OutputBuilder, ParseContext, ParserDescriptor, ParserOutput
from .tiff import parse_tiff
from .xmlmeta import parse_xmp_region


class WebPParser:
    descriptor = ParserDescriptor(
        name="WebP Parser",
        version="1.0",
        formats=("WEBP",),
        capability="good",
        description="RIFF/WebP chunks, dimensions, animation, EXIF, XMP, and ICC metadata",
    )

    def parse(self, reader: BinaryReader, context: ParseContext) -> ParserOutput:
        builder = OutputBuilder("webp", context.budget)
        root_id = builder.node("WEBP", "container", reader.base, reader.size)
        if reader.size < 12 or reader.read(0, 4) != b"RIFF" or reader.read(8, 4) != b"WEBP":
            builder.warn("webp.signature", "RIFF/WebP signature is missing", reader.base)
            return builder.output
        declared = reader.u32(4, "<") + 8
        if declared != reader.size:
            builder.warn("webp.size_mismatch", "RIFF declared size differs from actual file size", reader.base + 4)
        position = 12
        try:
            while position <= reader.size - 8:
                context.budget.check()
                chunk_type = reader.read(position, 4).decode("latin-1", errors="replace")
                length = reader.u32(position + 4, "<")
                padded = length + (length & 1)
                if padded > reader.size - position - 8:
                    builder.warn("webp.invalid_chunk_length", "{} chunk extends beyond the RIFF container".format(chunk_type), reader.base + position)
                    break
                payload = reader.subreader(position + 8, length)
                builder.node(chunk_type, "chunk", reader.base + position, 8 + padded, root_id, {"data_length": length})
                if chunk_type == "VP8X" and length >= 10:
                    flags = payload.u8(0)
                    width = payload.u24le(4) + 1
                    height = payload.u24le(7) + 1
                    builder.record("WebP", "Width", "WebP.Width", width, "media", offset=payload.base + 4, length=3)
                    builder.record("WebP", "Height", "WebP.Height", height, "media", offset=payload.base + 7, length=3)
                    builder.record("WebP", "Features", "WebP.Features", {"icc": bool(flags & 0x20), "alpha": bool(flags & 0x10), "exif": bool(flags & 0x08), "xmp": bool(flags & 0x04), "animation": bool(flags & 0x02)}, "media", offset=payload.base, length=1)
                elif chunk_type == "VP8 " and length >= 10 and payload.read(3, 3) == b"\x9d\x01\x2a":
                    builder.record("WebP", "Width", "WebP.Width", payload.u16(6, "<") & 0x3FFF, "media", offset=payload.base + 6, length=2)
                    builder.record("WebP", "Height", "WebP.Height", payload.u16(8, "<") & 0x3FFF, "media", offset=payload.base + 8, length=2)
                elif chunk_type == "VP8L" and length >= 5 and payload.u8(0) == 0x2F:
                    packed = payload.u32(1, "<")
                    builder.record("WebP", "Width", "WebP.Width", (packed & 0x3FFF) + 1, "media", offset=payload.base + 1, length=4)
                    builder.record("WebP", "Height", "WebP.Height", ((packed >> 14) & 0x3FFF) + 1, "media", offset=payload.base + 1, length=4)
                elif chunk_type == "EXIF":
                    start = 6 if length >= 6 and payload.read(0, 6) == b"Exif\x00\x00" else 0
                    builder.output.extend(parse_tiff(payload.subreader(start), context))
                elif chunk_type == "XMP ":
                    builder.output.extend(parse_xmp_region(payload, context))
                elif chunk_type == "ICCP":
                    builder.record("WebP", "ICCProfile", "WebP.ICCProfile", {"present": True, "length": length}, "media", offset=payload.base, length=length)
                elif chunk_type == "ANIM" and length >= 6:
                    builder.record("WebP", "Animated", "WebP.Animated", True, "media", offset=payload.base, length=length)
                    builder.record("WebP", "LoopCount", "WebP.LoopCount", payload.u16(4, "<"), "media", offset=payload.base + 4, length=2)
                position += 8 + padded
        except (BoundsError, LimitExceeded) as exc:
            builder.warn("webp.malformed", "WebP parsing stopped safely: {}".format(str(exc)), reader.base + min(position, reader.size))
        return builder.output

