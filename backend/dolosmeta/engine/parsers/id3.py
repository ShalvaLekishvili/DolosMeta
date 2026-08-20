"""Native ID3v1/v2 and basic MPEG audio metadata parsing."""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

from ..binary import BinaryReader
from ..errors import BoundsError, LimitExceeded
from .base import OutputBuilder, ParseContext, ParserDescriptor, ParserOutput, safe_text


FRAME_NAMES = {
    "TIT2": ("Title", "audio"),
    "TT2": ("Title", "audio"),
    "TPE1": ("Artist", "author"),
    "TP1": ("Artist", "author"),
    "TALB": ("Album", "audio"),
    "TAL": ("Album", "audio"),
    "TRCK": ("Track", "audio"),
    "TRK": ("Track", "audio"),
    "TCON": ("Genre", "audio"),
    "TCO": ("Genre", "audio"),
    "TYER": ("Year", "time"),
    "TYE": ("Year", "time"),
    "TDRC": ("RecordingTime", "time"),
    "TCOM": ("Composer", "author"),
    "TCM": ("Composer", "author"),
    "TENC": ("EncodedBy", "software"),
    "TEN": ("EncodedBy", "software"),
    "COMM": ("Comment", "document"),
    "COM": ("Comment", "document"),
    "WOAR": ("ArtistURL", "document"),
    "WAR": ("ArtistURL", "document"),
}

BITRATES = {
    # MPEG-1 Layer III in kbps
    1: (32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320),
    2: (8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),
}


def _synchsafe(data: bytes) -> int:
    if len(data) != 4 or any(byte & 0x80 for byte in data):
        raise ValueError("invalid synchsafe integer")
    return (data[0] << 21) | (data[1] << 14) | (data[2] << 7) | data[3]


def _deunsync(data: bytes) -> bytes:
    return data.replace(b"\xff\x00", b"\xff")


def _decode_text(data: bytes) -> str:
    if not data:
        return ""
    encoding_byte = data[0]
    payload = data[1:]
    encoding = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}.get(encoding_byte, "latin-1")
    try:
        return payload.decode(encoding, errors="replace").rstrip("\x00").replace("\x00", "; ")[:16_384]
    except LookupError:
        return safe_text(payload)


def _comment_text(data: bytes) -> str:
    if len(data) < 4:
        return _decode_text(data)
    encoding_byte = data[0]
    payload = bytes([encoding_byte]) + data[4:]
    decoded = _decode_text(payload)
    # Description and comment are separated after decoding; retain both if present.
    parts = [part for part in decoded.split("; ") if part]
    return parts[-1] if parts else decoded


def parse_id3(reader: BinaryReader, context: ParseContext, include_v1: bool = True) -> ParserOutput:
    builder = OutputBuilder("id3", context.budget)
    root_id = builder.node("ID3 / MPEG audio", "audio", reader.base, reader.size)
    audio_start = 0
    if reader.size >= 10 and reader.read(0, 3) == b"ID3":
        major = reader.u8(3)
        revision = reader.u8(4)
        flags = reader.u8(5)
        try:
            tag_size = _synchsafe(reader.read(6, 4))
        except ValueError:
            builder.warn("id3.invalid_size", "ID3 tag size is not synchsafe", reader.base + 6)
            tag_size = 0
        available = max(0, reader.size - 10)
        if tag_size > available or tag_size > context.budget.settings.max_metadata_block_bytes:
            builder.warn("id3.size_limit", "ID3 tag is truncated or exceeds the metadata limit", reader.base)
            tag_size = min(available, context.budget.settings.max_metadata_block_bytes)
        raw_tag = reader.read(10, tag_size)
        tag = _deunsync(raw_tag) if flags & 0x80 else raw_tag
        builder.record("ID3", "Version", "ID3.Version", "2.{}.{}".format(major, revision), "audio", offset=reader.base + 3, length=2)
        builder.record("ID3", "Unsynchronization", "ID3.Unsynchronization", bool(flags & 0x80), "audio", offset=reader.base + 5, length=1)
        position = 0
        if flags & 0x40 and len(tag) >= 4:
            try:
                extended = _synchsafe(tag[:4]) if major == 4 else int.from_bytes(tag[:4], "big") + 4
                position = min(len(tag), max(4, extended))
            except ValueError:
                builder.warn("id3.extended_header", "ID3 extended header is malformed")
        while position < len(tag):
            context.budget.check()
            header_size = 6 if major == 2 else 10
            if len(tag) - position < header_size:
                break
            frame_id_length = 3 if major == 2 else 4
            frame_id_raw = tag[position : position + frame_id_length]
            if frame_id_raw == b"\x00" * frame_id_length:
                break
            try:
                frame_id = frame_id_raw.decode("ascii")
            except UnicodeDecodeError:
                builder.warn("id3.frame_id", "Invalid ID3 frame identifier", reader.base + 10 + position)
                break
            if not re.match(r"^[A-Z0-9]{3,4}$", frame_id):
                builder.warn("id3.frame_id", "Invalid ID3 frame identifier {}".format(repr(frame_id)), reader.base + 10 + position)
                break
            if major == 2:
                frame_size = int.from_bytes(tag[position + 3 : position + 6], "big")
            elif major == 4:
                try:
                    frame_size = _synchsafe(tag[position + 4 : position + 8])
                except ValueError:
                    builder.warn("id3.frame_size", "Invalid ID3v2.4 frame size", reader.base + 10 + position)
                    break
            else:
                frame_size = int.from_bytes(tag[position + 4 : position + 8], "big")
            frame_start = position + header_size
            if frame_size < 0 or frame_size > len(tag) - frame_start:
                builder.warn("id3.truncated_frame", "{} frame is truncated".format(frame_id), reader.base + 10 + position)
                break
            frame = tag[frame_start : frame_start + frame_size]
            frame_node = builder.node(frame_id, "id3-frame", reader.base + 10 + position, header_size + frame_size, root_id, {"size": frame_size})
            definition = FRAME_NAMES.get(frame_id)
            if definition:
                name, category = definition
                if frame_id.startswith("T"):
                    value = _decode_text(frame)
                elif frame_id in {"COMM", "COM"}:
                    value = _comment_text(frame)
                else:
                    value = safe_text(frame, "latin-1")
                builder.record("ID3", name, "ID3.{}".format(frame_id), value, category, tag_id=frame_id, offset=reader.base + 10 + frame_start, length=frame_size)
            elif frame_id in {"APIC", "PIC"}:
                mime = "image/unknown"
                if frame_id == "APIC" and len(frame) > 2:
                    end = frame.find(b"\x00", 1, 256)
                    if end > 1:
                        mime = safe_text(frame[1:end], "latin-1", 255)
                builder.record("ID3", "AttachedPicture", "ID3.{}".format(frame_id), {"present": True, "mime": mime, "frame_length": frame_size}, "media", tag_id=frame_id, offset=reader.base + 10 + frame_start, length=frame_size)
            position = frame_start + frame_size
        audio_start = 10 + tag_size
    if include_v1 and reader.size >= 128 and reader.read(reader.size - 128, 3) == b"TAG":
        tail = reader.read(reader.size - 125, 125)
        for name, start, length, category in (
            ("Title", 0, 30, "audio"),
            ("Artist", 30, 30, "author"),
            ("Album", 60, 30, "audio"),
            ("Year", 90, 4, "time"),
            ("Comment", 94, 30, "document"),
        ):
            value = safe_text(tail[start : start + length], "latin-1")
            if value:
                builder.record("ID3v1", name, "ID3v1.{}".format(name), value, category, offset=reader.base + reader.size - 125 + start, length=length)
    # Locate a plausible MPEG frame near the end of ID3 metadata without scanning the whole file.
    scan_length = min(max(0, reader.size - audio_start), 64 * 1024)
    if scan_length >= 4:
        sample = reader.read(audio_start, scan_length)
        for index in range(len(sample) - 4):
            header = int.from_bytes(sample[index : index + 4], "big")
            if header & 0xFFE00000 != 0xFFE00000:
                continue
            version_bits = (header >> 19) & 0x3
            layer_bits = (header >> 17) & 0x3
            bitrate_index = (header >> 12) & 0xF
            sample_index = (header >> 10) & 0x3
            if layer_bits != 1 or bitrate_index in {0, 15} or sample_index == 3 or version_bits == 1:
                continue
            version = 1 if version_bits == 3 else 2
            rates = (44100, 48000, 32000) if version == 1 else ((22050, 24000, 16000) if version_bits == 2 else (11025, 12000, 8000))
            bitrate = BITRATES[version][bitrate_index - 1]
            builder.record("MPEG.Audio", "BitrateKbps", "MPEG.Audio.BitrateKbps", bitrate, "audio", offset=reader.base + audio_start + index, length=4)
            builder.record("MPEG.Audio", "SampleRate", "MPEG.Audio.SampleRate", rates[sample_index], "audio", offset=reader.base + audio_start + index, length=4)
            break
    return builder.output


class MP3Parser:
    descriptor = ParserDescriptor(
        name="MP3/ID3 Parser",
        version="1.0",
        formats=("MP3",),
        capability="good",
        description="Native ID3v1, ID3v2.2/v2.3/v2.4 and basic MPEG audio inspection",
    )

    def parse(self, reader: BinaryReader, context: ParseContext) -> ParserOutput:
        return parse_id3(reader, context)

