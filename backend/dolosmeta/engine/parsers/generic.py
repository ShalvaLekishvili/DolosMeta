"""Useful bounded metadata for simpler and otherwise unsupported formats."""

from __future__ import annotations

import json

from defusedxml import ElementTree

from ..binary import BinaryReader
from ..errors import BoundsError
from .base import OutputBuilder, ParseContext, ParserDescriptor, ParserOutput, safe_text


class GenericParser:
    descriptor = ParserDescriptor(
        name="Generic Parser",
        version="1.0",
        formats=("Unknown", "Text", "JSON", "XML", "GIF", "BMP", "SQLite", "FLAC", "OGG", "RAR", "7Z"),
        capability="basic",
        description="Generic structure plus basic metadata for text and common lightweight formats",
    )

    def parse(self, reader: BinaryReader, context: ParseContext) -> ParserOutput:
        builder = OutputBuilder("generic", context.budget)
        fmt = context.detection.format
        root_id = builder.node(fmt, "file", reader.base, reader.size)
        try:
            if fmt == "GIF" and reader.size >= 13:
                builder.record("GIF", "Version", "GIF.Version", safe_text(reader.read(3, 3), "ascii", 3), "media")
                builder.record("GIF", "Width", "GIF.Width", reader.u16(6, "<"), "media")
                builder.record("GIF", "Height", "GIF.Height", reader.u16(8, "<"), "media")
                packed = reader.u8(10)
                builder.record("GIF", "ColorResolution", "GIF.ColorResolution", ((packed >> 4) & 0x07) + 1, "media")
            elif fmt == "BMP" and reader.size >= 30:
                dib = reader.u32(14, "<")
                if dib >= 40 and reader.size >= 54:
                    builder.record("BMP", "Width", "BMP.Width", reader.i32(18, "<"), "media")
                    builder.record("BMP", "Height", "BMP.Height", reader.i32(22, "<"), "media")
                    builder.record("BMP", "BitsPerPixel", "BMP.BitsPerPixel", reader.u16(28, "<"), "media")
                    builder.record("BMP", "Compression", "BMP.Compression", reader.u32(30, "<"), "media")
            elif fmt == "SQLite" and reader.size >= 100:
                page_size = reader.u16(16, ">") or 65536
                builder.record("SQLite", "PageSize", "SQLite.PageSize", page_size, "document")
                builder.record("SQLite", "WriteVersion", "SQLite.WriteVersion", reader.u8(18), "document")
                builder.record("SQLite", "ReadVersion", "SQLite.ReadVersion", reader.u8(19), "document")
                builder.record("SQLite", "PageCount", "SQLite.PageCount", reader.u32(28, ">"), "document")
            elif fmt == "FLAC" and reader.size >= 42 and reader.read(0, 4) == b"fLaC":
                block_header = reader.read(4, 4)
                block_type = block_header[0] & 0x7F
                block_length = int.from_bytes(block_header[1:4], "big")
                if block_type == 0 and block_length >= 34 and reader.size >= 8 + block_length:
                    info = reader.read(8, 34)
                    packed = int.from_bytes(info[10:18], "big")
                    sample_rate = (packed >> 44) & 0xFFFFF
                    channels = ((packed >> 41) & 0x7) + 1
                    bit_depth = ((packed >> 36) & 0x1F) + 1
                    samples = packed & 0xFFFFFFFFF
                    for name, value in (("SampleRate", sample_rate), ("Channels", channels), ("BitDepth", bit_depth), ("TotalSamples", samples)):
                        builder.record("FLAC", name, "FLAC.{}".format(name), value, "audio")
                    if sample_rate:
                        builder.record("FLAC", "Duration", "FLAC.Duration", round(samples / sample_rate, 6), "audio")
            elif fmt == "OGG" and reader.size >= 27:
                builder.record("Ogg", "StreamSerial", "Ogg.StreamSerial", reader.u32(14, "<"), "media")
                builder.record("Ogg", "PageSequence", "Ogg.PageSequence", reader.u32(18, "<"), "media")
            elif fmt in {"Text", "JSON", "XML"}:
                maximum = min(reader.size, context.budget.settings.max_metadata_block_bytes)
                data = reader.read(0, maximum)
                if maximum < reader.size:
                    builder.warn("generic.text_limit", "Text inspection was truncated by the metadata limit")
                text = data.decode("utf-8", errors="replace")
                builder.record("Text", "Encoding", "Text.Encoding", "UTF-8" if "\ufffd" not in text else "UTF-8 with replacement characters", "document")
                builder.record("Text", "LineCountObserved", "Text.LineCountObserved", text.count("\n") + int(bool(text)), "document")
                if fmt == "JSON":
                    try:
                        parsed = json.loads(text)
                        builder.record("JSON", "RootType", "JSON.RootType", type(parsed).__name__, "document")
                        if isinstance(parsed, (dict, list)):
                            builder.record("JSON", "RootItemCount", "JSON.RootItemCount", len(parsed), "document")
                    except (ValueError, RecursionError):
                        builder.warn("json.malformed", "JSON text could not be decoded")
                elif fmt == "XML":
                    if b"<!DOCTYPE" in data[:4096].upper() or b"<!ENTITY" in data[:4096].upper():
                        builder.warn("xml.forbidden_declaration", "DTD/entity declarations are not permitted")
                    else:
                        try:
                            root = ElementTree.fromstring(data)
                            builder.record("XML", "RootElement", "XML.RootElement", root.tag, "document")
                        except Exception as exc:
                            builder.warn("xml.malformed", "XML could not be parsed: {}".format(type(exc).__name__))
        except (BoundsError, ValueError) as exc:
            builder.warn("generic.malformed", "Basic format inspection stopped safely: {}".format(str(exc)), reader.base)
        return builder.output

