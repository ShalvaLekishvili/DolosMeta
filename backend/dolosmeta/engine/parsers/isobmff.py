"""Native ISO Base Media File Format / QuickTime box walker."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from ..binary import BinaryReader
from ..errors import BoundsError, LimitExceeded
from .base import OutputBuilder, ParseContext, ParserDescriptor, ParserOutput, safe_text


CONTAINERS = {"moov", "trak", "mdia", "minf", "stbl", "dinf", "edts", "udta", "meta", "ilst", "moof", "traf", "mfra", "skip"}
ILST_NAMES = {
    "\xa9nam": "Title",
    "\xa9ART": "Artist",
    "aART": "AlbumArtist",
    "\xa9alb": "Album",
    "\xa9day": "Date",
    "\xa9too": "Encoder",
    "\xa9cmt": "Comment",
    "\xa9gen": "Genre",
    "\xa9xyz": "Location",
}


def _quicktime_time(value: int) -> Optional[str]:
    if value == 0:
        return None
    try:
        result = datetime(1904, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=value)
        if result.year < 1970 or result.year > 3000:
            return None
        return result.isoformat().replace("+00:00", "Z")
    except (OverflowError, ValueError):
        return None


class ISOBMFFParser:
    descriptor = ParserDescriptor(
        name="ISO BMFF Parser",
        version="1.0",
        formats=("MP4", "MOV", "M4A"),
        capability="good",
        description="ISO BMFF/QuickTime box tree, timing, tracks, dimensions, codecs, and item metadata",
    )

    def parse(self, reader: BinaryReader, context: ParseContext) -> ParserOutput:
        builder = OutputBuilder("iso-bmff", context.budget)
        root_id = builder.node(context.detection.format, "container", reader.base, reader.size)
        track_count = [0]
        try:
            self._walk(reader, 0, reader.size, root_id, 0, context, builder, track_count, None)
            builder.record("ISO.BMFF", "TrackCount", "ISO.BMFF.TrackCount", track_count[0], "video")
        except (BoundsError, LimitExceeded) as exc:
            builder.warn("bmff.malformed", "ISO BMFF parsing stopped safely: {}".format(str(exc)), reader.base)
        return builder.output

    def _walk(
        self,
        reader: BinaryReader,
        start: int,
        end: int,
        parent_id: str,
        depth: int,
        context: ParseContext,
        builder: OutputBuilder,
        track_count: list,
        parent_type: Optional[str],
    ) -> None:
        context.budget.depth(depth)
        position = start
        while position <= end - 8:
            context.budget.check()
            size32 = reader.u32(position, ">")
            type_raw = reader.read(position + 4, 4)
            box_type = type_raw.decode("latin-1", errors="replace")
            header = 8
            if size32 == 1:
                if position > end - 16:
                    builder.warn("bmff.truncated_extended_size", "Extended-size box header is truncated", reader.base + position)
                    return
                box_size = reader.u64(position + 8, ">")
                header = 16
            elif size32 == 0:
                box_size = end - position
            else:
                box_size = size32
            if box_size < header or box_size > end - position:
                builder.warn("bmff.invalid_box_size", "{} box has an invalid size".format(box_type), reader.base + position)
                return
            payload_start = position + header
            payload_length = box_size - header
            node_id = builder.node(box_type, "box", reader.base + position, box_size, parent_id, {"header_size": header, "data_length": payload_length})
            payload = reader.subreader(payload_start, payload_length)
            if box_type == "ftyp" and payload_length >= 8:
                brand = safe_text(payload.read(0, 4), "latin-1", 4)
                minor = payload.u32(4, ">")
                compatibles = [safe_text(payload.read(offset, 4), "latin-1", 4) for offset in range(8, payload_length - 3, 4)][:64]
                builder.record("ISO.BMFF", "MajorBrand", "ISO.BMFF.MajorBrand", brand, "media", offset=payload.base, length=4)
                builder.record("ISO.BMFF", "MinorVersion", "ISO.BMFF.MinorVersion", minor, "media", offset=payload.base + 4, length=4)
                builder.record("ISO.BMFF", "CompatibleBrands", "ISO.BMFF.CompatibleBrands", compatibles, "media", offset=payload.base + 8, length=max(0, payload_length - 8))
            elif box_type == "mvhd":
                self._parse_mvhd(payload, builder)
            elif box_type == "tkhd":
                self._parse_tkhd(payload, builder)
            elif box_type == "mdhd":
                self._parse_mdhd(payload, builder)
            elif box_type == "hdlr" and payload_length >= 12:
                handler = safe_text(payload.read(8, 4), "latin-1", 4)
                name = safe_text(payload.read(24, min(1024, payload_length - 24)), "utf-8") if payload_length > 24 else ""
                builder.record("ISO.Track", "HandlerType", "ISO.Track.HandlerType", handler, "video", offset=payload.base + 8, length=4)
                if name:
                    builder.record("ISO.Track", "HandlerName", "ISO.Track.HandlerName", name, "video", offset=payload.base + 24, length=min(1024, payload_length - 24))
            elif box_type == "stsd" and payload_length >= 16:
                count = payload.u32(4, ">")
                codec = safe_text(payload.read(12, 4), "latin-1", 4)
                builder.record("ISO.Track", "SampleDescriptionCount", "ISO.Track.SampleDescriptionCount", count, "video", offset=payload.base + 4, length=4)
                builder.record("ISO.Track", "Codec", "ISO.Track.Codec", codec, "video", offset=payload.base + 12, length=4)
            elif parent_type == "ilst":
                self._parse_ilst_atom(box_type, payload, builder)
            if box_type == "trak":
                track_count[0] += 1
            if box_type in CONTAINERS and payload_length >= 8:
                child_start = payload_start + (4 if box_type == "meta" and payload_length >= 4 else 0)
                self._walk(reader, child_start, position + box_size, node_id, depth + 1, context, builder, track_count, box_type)
            position += box_size

    def _parse_mvhd(self, payload: BinaryReader, builder: OutputBuilder) -> None:
        if payload.size < 20:
            builder.warn("bmff.mvhd_truncated", "mvhd box is truncated", payload.base)
            return
        version = payload.u8(0)
        if version == 1 and payload.size >= 32:
            created, modified = payload.u64(4, ">"), payload.u64(12, ">")
            timescale, duration = payload.u32(20, ">"), payload.u64(24, ">")
        else:
            created, modified = payload.u32(4, ">"), payload.u32(8, ">")
            timescale, duration = payload.u32(12, ">"), payload.u32(16, ">")
        for name, raw in (("CreationTime", created), ("ModificationTime", modified)):
            value = _quicktime_time(raw)
            if value:
                builder.record("ISO.Movie", name, "ISO.Movie.{}".format(name), value, "time")
        builder.record("ISO.Movie", "Timescale", "ISO.Movie.Timescale", timescale, "video")
        if timescale:
            builder.record("ISO.Movie", "Duration", "ISO.Movie.Duration", round(duration / timescale, 6), "video", description="Duration derived from media duration and timescale")

    def _parse_tkhd(self, payload: BinaryReader, builder: OutputBuilder) -> None:
        if payload.size < 84:
            builder.warn("bmff.tkhd_truncated", "tkhd box is truncated", payload.base)
            return
        version = payload.u8(0)
        if version == 1 and payload.size >= 96:
            track_id = payload.u32(20, ">")
            matrix_offset, dimension_offset = 52, 88
        else:
            track_id = payload.u32(12, ">")
            matrix_offset, dimension_offset = 40, 76
        builder.record("ISO.Track", "TrackID", "ISO.Track.TrackID", track_id, "video")
        if payload.size >= dimension_offset + 8:
            width = payload.u32(dimension_offset, ">") / 65536.0
            height = payload.u32(dimension_offset + 4, ">") / 65536.0
            if width:
                builder.record("ISO.Track", "Width", "ISO.Track.Width", round(width, 3), "video")
            if height:
                builder.record("ISO.Track", "Height", "ISO.Track.Height", round(height, 3), "video")
        if payload.size >= matrix_offset + 20:
            a = payload.i32(matrix_offset, ">") / 65536.0
            b = payload.i32(matrix_offset + 4, ">") / 65536.0
            c = payload.i32(matrix_offset + 12, ">") / 65536.0
            d = payload.i32(matrix_offset + 16, ">") / 65536.0
            rotation = None
            if round(a) == 0 and round(b) == 1 and round(c) == -1 and round(d) == 0:
                rotation = 90
            elif round(a) == -1 and round(d) == -1:
                rotation = 180
            elif round(a) == 0 and round(b) == -1 and round(c) == 1 and round(d) == 0:
                rotation = 270
            if rotation is not None:
                builder.record("ISO.Track", "Rotation", "ISO.Track.Rotation", rotation, "video")

    def _parse_mdhd(self, payload: BinaryReader, builder: OutputBuilder) -> None:
        if payload.size < 20:
            return
        version = payload.u8(0)
        if version == 1 and payload.size >= 32:
            timescale, duration = payload.u32(20, ">"), payload.u64(24, ">")
        else:
            timescale, duration = payload.u32(12, ">"), payload.u32(16, ">")
        builder.record("ISO.Track", "MediaTimescale", "ISO.Track.MediaTimescale", timescale, "video")
        if timescale:
            builder.record("ISO.Track", "MediaDuration", "ISO.Track.MediaDuration", round(duration / timescale, 6), "video")

    def _parse_ilst_atom(self, atom_type: str, payload: BinaryReader, builder: OutputBuilder) -> None:
        name = ILST_NAMES.get(atom_type, "Tag_{}".format(atom_type.encode("latin-1", errors="replace").hex()))
        if payload.size < 16 or payload.read(4, 4) != b"data":
            return
        data_box_size = payload.u32(0, ">")
        if data_box_size < 16 or data_box_size > payload.size:
            return
        raw = payload.read(16, min(data_box_size - 16, 16_384))
        value = safe_text(raw, "utf-8")
        if value:
            category = "location" if name == "Location" else ("author" if "Artist" in name else ("software" if name == "Encoder" else "audio"))
            builder.record("QuickTime.ItemList", name, "QuickTime.ItemList.{}".format(name), value, category, offset=payload.base + 16, length=len(raw))

