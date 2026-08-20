"""Native JPEG marker, EXIF/TIFF, XMP, ICC, and IPTC inspection."""

from __future__ import annotations

from typing import Dict, Optional

from ..binary import BinaryReader
from ..errors import BoundsError, LimitExceeded
from .base import OutputBuilder, ParseContext, ParserDescriptor, ParserOutput, safe_text
from .tiff import parse_tiff
from .xmlmeta import parse_xmp_region


MARKERS = {
    0xD8: "SOI",
    0xD9: "EOI",
    0xDA: "SOS",
    0xDB: "DQT",
    0xC4: "DHT",
    0xDD: "DRI",
    0xFE: "COM",
    0xC0: "SOF0",
    0xC1: "SOF1",
    0xC2: "SOF2",
    0xC3: "SOF3",
    0xE0: "APP0",
    0xE1: "APP1",
    0xE2: "APP2",
    0xED: "APP13",
    0xEE: "APP14",
}

IPTC_TAGS = {
    (2, 5): ("ObjectName", "document"),
    (2, 25): ("Keywords", "document"),
    (2, 55): ("DateCreated", "time"),
    (2, 60): ("TimeCreated", "time"),
    (2, 80): ("By-line", "author"),
    (2, 90): ("City", "location"),
    (2, 95): ("ProvinceState", "location"),
    (2, 101): ("Country", "location"),
    (2, 110): ("Credit", "author"),
    (2, 115): ("Source", "author"),
    (2, 116): ("CopyrightNotice", "author"),
    (2, 120): ("Caption", "document"),
}


def _parse_iptc(data: bytes, absolute_offset: int, context: ParseContext) -> ParserOutput:
    builder = OutputBuilder("iptc", context.budget)
    position = 0
    while position + 5 <= len(data):
        marker = data.find(b"\x1c", position)
        if marker < 0 or marker + 5 > len(data):
            break
        record = data[marker + 1]
        dataset = data[marker + 2]
        length = int.from_bytes(data[marker + 3 : marker + 5], "big")
        value_start = marker + 5
        if length & 0x8000:
            octets = length & 0x7FFF
            if octets == 0 or octets > 4 or value_start + octets > len(data):
                builder.warn("iptc.invalid_length", "Invalid extended IPTC length", absolute_offset + marker)
                break
            length = int.from_bytes(data[value_start : value_start + octets], "big")
            value_start += octets
        if length > len(data) - value_start:
            builder.warn("iptc.truncated", "IPTC dataset is truncated", absolute_offset + marker)
            break
        definition = IPTC_TAGS.get((record, dataset))
        name, category = definition or ("Unknown{}:{}".format(record, dataset), "unknown")
        raw = data[value_start : value_start + length]
        builder.record(
            "IPTC",
            name,
            "IPTC.{}.{}".format(record, dataset),
            safe_text(raw),
            category,
            tag_id="{}:{}".format(record, dataset),
            offset=absolute_offset + value_start,
            length=length,
        )
        position = value_start + length
    return builder.output


class JPEGParser:
    descriptor = ParserDescriptor(
        name="JPEG Parser",
        version="1.0",
        formats=("JPEG",),
        capability="full",
        description="JPEG marker inventory with native EXIF, XMP, ICC, and IPTC parsing",
    )

    def parse(self, reader: BinaryReader, context: ParseContext) -> ParserOutput:
        builder = OutputBuilder("jpeg", context.budget)
        root_id = builder.node("JPEG", "container", reader.base, reader.size)
        if reader.size < 2 or reader.read(0, 2) != b"\xff\xd8":
            builder.warn("jpeg.signature", "JPEG SOI marker is missing", reader.base)
            return builder.output
        builder.node("SOI", "marker", reader.base, 2, root_id)
        position = 2
        try:
            while position < reader.size:
                context.budget.check()
                if reader.u8(position) != 0xFF:
                    next_marker = reader.read(position, min(reader.size - position, 4096)).find(b"\xff")
                    if next_marker < 0:
                        builder.warn("jpeg.marker_sync", "Could not locate the next JPEG marker", reader.base + position)
                        break
                    builder.warn("jpeg.padding", "Unexpected bytes before JPEG marker", reader.base + position)
                    position += next_marker
                while position < reader.size and reader.u8(position) == 0xFF:
                    position += 1
                if position >= reader.size:
                    break
                marker = reader.u8(position)
                marker_start = position - 1
                position += 1
                name = MARKERS.get(marker, "MARKER_FF{:02X}".format(marker))
                if marker == 0xD9:
                    builder.node(name, "marker", reader.base + marker_start, 2, root_id)
                    break
                if marker in {0xD8, 0x01} or 0xD0 <= marker <= 0xD7:
                    builder.node(name, "marker", reader.base + marker_start, 2, root_id)
                    continue
                if position > reader.size - 2:
                    builder.warn("jpeg.truncated_length", "JPEG marker length is truncated", reader.base + marker_start)
                    break
                segment_length = reader.u16(position, ">")
                if segment_length < 2 or segment_length > reader.size - position:
                    builder.warn("jpeg.invalid_length", "JPEG segment length is outside the file", reader.base + marker_start)
                    break
                payload_offset = position + 2
                payload_length = segment_length - 2
                node_id = builder.node(name, "segment", reader.base + marker_start, segment_length + 2, root_id, {"marker": "FF{:02X}".format(marker)})
                if marker == 0xDA:
                    builder.node("Entropy-coded image data", "data", reader.base + payload_offset + payload_length, max(0, reader.size - payload_offset - payload_length), node_id)
                    break
                payload = reader.subreader(payload_offset, payload_length)
                if marker == 0xE0 and payload_length >= 5 and payload.read(0, 5) == b"JFIF\x00":
                    builder.record("JFIF", "Identifier", "JFIF.Identifier", "JFIF", "media", offset=payload.base, length=5)
                    if payload_length >= 14:
                        builder.record("JFIF", "Version", "JFIF.Version", "{}.{}".format(payload.u8(5), payload.u8(6)), "media", offset=payload.base + 5, length=2)
                        builder.record("JFIF", "DensityUnits", "JFIF.DensityUnits", payload.u8(7), "media", offset=payload.base + 7, length=1)
                        builder.record("JFIF", "XDensity", "JFIF.XDensity", payload.u16(8, ">"), "media", offset=payload.base + 8, length=2)
                        builder.record("JFIF", "YDensity", "JFIF.YDensity", payload.u16(10, ">"), "media", offset=payload.base + 10, length=2)
                elif marker == 0xE1 and payload_length >= 6 and payload.read(0, 6) == b"Exif\x00\x00":
                    builder.output.extend(parse_tiff(payload.subreader(6), context))
                elif marker == 0xE1:
                    prefix = b"http://ns.adobe.com/xap/1.0/\x00"
                    if payload_length > len(prefix) and payload.read(0, len(prefix)) == prefix:
                        builder.output.extend(parse_xmp_region(payload.subreader(len(prefix)), context))
                elif marker == 0xE2 and payload_length >= 12 and payload.read(0, 12) == b"ICC_PROFILE\x00":
                    builder.record("ICC", "ProfileChunk", "ICC.ProfileChunk", {"sequence": payload.u8(12) if payload_length > 12 else None, "total": payload.u8(13) if payload_length > 13 else None, "length": max(0, payload_length - 14)}, "media", offset=payload.base, length=payload_length)
                elif marker == 0xED:
                    data = payload.read(0, min(payload_length, context.budget.settings.max_metadata_block_bytes))
                    builder.output.extend(_parse_iptc(data, payload.base, context))
                elif marker == 0xFE:
                    builder.record("JPEG", "Comment", "JPEG.Comment", safe_text(payload.read(0, min(payload_length, 16_384))), "document", offset=payload.base, length=payload_length)
                elif marker in {0xC0, 0xC1, 0xC2, 0xC3} and payload_length >= 6:
                    precision = payload.u8(0)
                    height = payload.u16(1, ">")
                    width = payload.u16(3, ">")
                    components = payload.u8(5)
                    builder.record("JPEG", "Width", "JPEG.Width", width, "media", offset=payload.base + 3, length=2)
                    builder.record("JPEG", "Height", "JPEG.Height", height, "media", offset=payload.base + 1, length=2)
                    builder.record("JPEG", "Precision", "JPEG.Precision", precision, "media", offset=payload.base, length=1)
                    builder.record("JPEG", "Components", "JPEG.Components", components, "media", offset=payload.base + 5, length=1)
                position += segment_length
        except (BoundsError, LimitExceeded) as exc:
            builder.warn("jpeg.malformed", "JPEG parsing stopped safely: {}".format(str(exc)), reader.base + min(position, reader.size))
        return builder.output

