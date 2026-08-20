"""Native PNG chunk inventory and bounded metadata decoding."""

from __future__ import annotations

import zlib
from typing import Optional, Tuple

from ..binary import BinaryReader
from ..errors import BoundsError, LimitExceeded
from .base import OutputBuilder, ParseContext, ParserDescriptor, ParserOutput, safe_text
from .tiff import parse_tiff
from .xmlmeta import parse_xmp_bytes


COLOR_TYPES = {
    0: "grayscale",
    2: "truecolor",
    3: "indexed-color",
    4: "grayscale with alpha",
    6: "truecolor with alpha",
}


def _bounded_inflate(data: bytes, context: ParseContext, builder: OutputBuilder) -> Optional[bytes]:
    remaining = context.budget.settings.max_decompressed_bytes - context.budget.decompressed_bytes
    if remaining <= 0:
        builder.warn("compression.limit", "No decompression budget remains")
        return None
    try:
        decompressor = zlib.decompressobj()
        result = decompressor.decompress(data, remaining + 1)
        if len(result) > remaining or decompressor.unconsumed_tail:
            builder.warn("compression.limit", "Compressed metadata exceeded the decompression limit")
            context.budget.note("decompression limit reached")
            return None
        result += decompressor.flush(max(0, remaining - len(result)))
        context.budget.claim_decompressed(len(result))
        return result
    except (zlib.error, ValueError) as exc:
        builder.warn("compression.invalid", "Compressed metadata is invalid: {}".format(type(exc).__name__))
        return None


def _split_nul(data: bytes) -> Tuple[bytes, bytes]:
    if b"\x00" not in data:
        return data, b""
    return data.split(b"\x00", 1)


class PNGParser:
    descriptor = ParserDescriptor(
        name="PNG Parser",
        version="1.0",
        formats=("PNG",),
        capability="full",
        description="PNG chunk inventory, textual metadata, EXIF, color, and profile inspection",
    )

    def parse(self, reader: BinaryReader, context: ParseContext) -> ParserOutput:
        builder = OutputBuilder("png", context.budget)
        root_id = builder.node("PNG", "container", reader.base, reader.size)
        if reader.size < 8 or reader.read(0, 8) != b"\x89PNG\r\n\x1a\n":
            builder.warn("png.signature", "PNG signature is missing", reader.base)
            return builder.output
        position = 8
        chunk_index = 0
        try:
            while position <= reader.size - 12:
                context.budget.check()
                length = reader.u32(position, ">")
                chunk_type_raw = reader.read(position + 4, 4)
                chunk_type = chunk_type_raw.decode("latin-1", errors="replace")
                if length > reader.size - position - 12:
                    builder.warn("png.invalid_chunk_length", "{} chunk extends beyond the file".format(chunk_type), reader.base + position)
                    break
                data_offset = position + 8
                total = length + 12
                stored_crc = reader.u32(data_offset + length, ">")
                computed_crc = zlib.crc32(chunk_type_raw)
                # Avoid reading large image-data chunks merely to recompute their CRC.
                crc_checked = length <= context.budget.settings.max_metadata_block_bytes and chunk_type != "IDAT"
                if crc_checked:
                    computed_crc = zlib.crc32(reader.read(data_offset, length), computed_crc) & 0xFFFFFFFF
                    if computed_crc != stored_crc:
                        builder.warn("png.crc_mismatch", "{} chunk CRC does not match".format(chunk_type), reader.base + position)
                node_id = builder.node(chunk_type, "chunk", reader.base + position, total, root_id, {"data_length": length, "crc_checked": crc_checked})
                chunk_index += 1
                if chunk_index > context.budget.settings.max_structure_nodes:
                    builder.warn("png.chunk_limit", "PNG chunk inventory was truncated")
                    break
                payload = reader.subreader(data_offset, length)
                if chunk_type == "IHDR" and length == 13:
                    width = payload.u32(0, ">")
                    height = payload.u32(4, ">")
                    bit_depth = payload.u8(8)
                    color_type = payload.u8(9)
                    for name, value in (
                        ("Width", width),
                        ("Height", height),
                        ("BitDepth", bit_depth),
                        ("ColorType", COLOR_TYPES.get(color_type, color_type)),
                        ("CompressionMethod", payload.u8(10)),
                        ("FilterMethod", payload.u8(11)),
                        ("InterlaceMethod", payload.u8(12)),
                    ):
                        builder.record("PNG", name, "PNG.{}".format(name), value, "media", offset=payload.base, length=length)
                elif chunk_type == "tEXt" and length <= context.budget.settings.max_metadata_block_bytes:
                    keyword, text = _split_nul(payload.read(0, length))
                    name = safe_text(keyword, "latin-1", 79) or "Text"
                    builder.record("PNG.Text", name, "PNG.Text.{}".format(name), safe_text(text, "latin-1"), "document", offset=payload.base, length=length)
                elif chunk_type == "zTXt" and length <= context.budget.settings.max_metadata_block_bytes:
                    keyword, remainder = _split_nul(payload.read(0, length))
                    if len(remainder) >= 1 and remainder[0] == 0:
                        value = _bounded_inflate(remainder[1:], context, builder)
                        if value is not None:
                            name = safe_text(keyword, "latin-1", 79) or "CompressedText"
                            builder.record("PNG.Text", name, "PNG.Text.{}".format(name), safe_text(value, "latin-1"), "document", offset=payload.base, length=length)
                elif chunk_type == "iTXt" and length <= context.budget.settings.max_metadata_block_bytes:
                    raw = payload.read(0, length)
                    keyword, rest = _split_nul(raw)
                    if len(rest) >= 2:
                        compressed = rest[0] == 1
                        rest = rest[2:]
                        language, rest = _split_nul(rest)
                        translated, text = _split_nul(rest)
                        if compressed:
                            inflated = _bounded_inflate(text, context, builder)
                            text = inflated if inflated is not None else b""
                        name = safe_text(keyword, "latin-1", 79) or "InternationalText"
                        value = safe_text(text, "utf-8")
                        builder.record("PNG.Text", name, "PNG.Text.{}".format(name), value, "document", offset=payload.base, length=length)
                        if "xmp" in name.lower() and value:
                            builder.output.extend(parse_xmp_bytes(text, context, payload.base))
                elif chunk_type == "eXIf":
                    builder.output.extend(parse_tiff(payload, context))
                elif chunk_type == "pHYs" and length == 9:
                    builder.record("PNG", "PixelsPerUnitX", "PNG.PixelsPerUnitX", payload.u32(0, ">"), "media", offset=payload.base, length=4)
                    builder.record("PNG", "PixelsPerUnitY", "PNG.PixelsPerUnitY", payload.u32(4, ">"), "media", offset=payload.base + 4, length=4)
                    builder.record("PNG", "PixelUnit", "PNG.PixelUnit", payload.u8(8), "media", offset=payload.base + 8, length=1)
                elif chunk_type == "tIME" and length == 7:
                    stamp = "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}".format(payload.u16(0, ">"), payload.u8(2), payload.u8(3), payload.u8(4), payload.u8(5), payload.u8(6))
                    builder.record("PNG", "ModificationTime", "PNG.ModificationTime", stamp, "time", offset=payload.base, length=7)
                elif chunk_type in {"gAMA", "cHRM", "sRGB", "iCCP"}:
                    builder.record("PNG", "{}Present".format(chunk_type), "PNG.{}Present".format(chunk_type), True, "media", offset=payload.base, length=length)
                position += total
                if chunk_type == "IEND":
                    break
            if position < reader.size and not any(node.label == "IEND" for node in builder.output.structure):
                builder.warn("png.missing_iend", "PNG IEND chunk was not observed")
        except (BoundsError, LimitExceeded) as exc:
            builder.warn("png.malformed", "PNG parsing stopped safely: {}".format(str(exc)), reader.base + min(position, reader.size))
        return builder.output

