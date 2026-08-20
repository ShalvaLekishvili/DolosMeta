"""Native RIFF/WAVE and basic AVI chunk inspection."""

from __future__ import annotations

from ..binary import BinaryReader
from ..errors import BoundsError, LimitExceeded
from .base import OutputBuilder, ParseContext, ParserDescriptor, ParserOutput, safe_text
from .id3 import parse_id3


INFO_NAMES = {
    "IART": ("Artist", "author"),
    "INAM": ("Title", "audio"),
    "IPRD": ("Product", "audio"),
    "ICRD": ("CreationDate", "time"),
    "IGNR": ("Genre", "audio"),
    "ICMT": ("Comment", "document"),
    "ISFT": ("Software", "software"),
    "ICOP": ("Copyright", "author"),
}


class RIFFParser:
    descriptor = ParserDescriptor(
        name="RIFF/WAVE Parser",
        version="1.0",
        formats=("WAV", "AVI"),
        capability="good",
        description="RIFF chunk inventory, WAVE format, INFO, BEXT, and embedded ID3 inspection",
    )

    def parse(self, reader: BinaryReader, context: ParseContext) -> ParserOutput:
        builder = OutputBuilder("riff", context.budget)
        subtype = reader.read(8, 4).decode("latin-1", errors="replace") if reader.size >= 12 else ""
        root_id = builder.node("RIFF/{}".format(subtype), "container", reader.base, reader.size)
        if reader.size < 12 or reader.read(0, 4) != b"RIFF":
            builder.warn("riff.signature", "RIFF signature is missing", reader.base)
            return builder.output
        declared = reader.u32(4, "<") + 8
        if declared != reader.size:
            builder.warn("riff.size_mismatch", "RIFF declared size differs from actual size", reader.base + 4)
        position = 12
        byte_rate = None
        data_length = None
        try:
            while position <= reader.size - 8:
                context.budget.check()
                chunk_id = reader.read(position, 4).decode("latin-1", errors="replace")
                length = reader.u32(position + 4, "<")
                padded = length + (length & 1)
                if padded > reader.size - position - 8:
                    builder.warn("riff.invalid_chunk_length", "{} chunk extends outside RIFF".format(chunk_id), reader.base + position)
                    break
                payload = reader.subreader(position + 8, length)
                node_id = builder.node(chunk_id, "chunk", reader.base + position, 8 + padded, root_id, {"data_length": length})
                if chunk_id == "fmt " and length >= 16:
                    fields = (
                        ("AudioFormat", payload.u16(0, "<")),
                        ("Channels", payload.u16(2, "<")),
                        ("SampleRate", payload.u32(4, "<")),
                        ("ByteRate", payload.u32(8, "<")),
                        ("BlockAlign", payload.u16(12, "<")),
                        ("BitsPerSample", payload.u16(14, "<")),
                    )
                    byte_rate = fields[3][1]
                    for name, value in fields:
                        builder.record("WAVE", name, "WAVE.{}".format(name), value, "audio", offset=payload.base, length=length)
                elif chunk_id == "data":
                    data_length = length
                    builder.record("WAVE", "AudioDataLength", "WAVE.AudioDataLength", length, "audio", offset=payload.base, length=length)
                elif chunk_id == "bext" and length >= 256:
                    description = safe_text(payload.read(0, min(256, length)), "ascii", 256)
                    originator = safe_text(payload.read(256, min(32, max(0, length - 256))), "ascii", 32) if length > 256 else ""
                    builder.record("BWF", "Description", "BWF.Description", description, "document", offset=payload.base, length=min(256, length))
                    if originator:
                        builder.record("BWF", "Originator", "BWF.Originator", originator, "author", offset=payload.base + 256, length=min(32, length - 256))
                elif chunk_id in {"ID3 ", "id3 "}:
                    builder.output.extend(parse_id3(payload, context, include_v1=False))
                elif chunk_id == "LIST" and length >= 4 and payload.read(0, 4) == b"INFO":
                    inner = 4
                    while inner <= length - 8:
                        info_id = payload.read(inner, 4).decode("latin-1", errors="replace")
                        info_length = payload.u32(inner + 4, "<")
                        info_padded = info_length + (info_length & 1)
                        if info_padded > length - inner - 8:
                            builder.warn("riff.info_truncated", "RIFF INFO subchunk is truncated", payload.base + inner)
                            break
                        value = safe_text(payload.read(inner + 8, min(info_length, 16_384)), "latin-1")
                        name, category = INFO_NAMES.get(info_id, (info_id, "unknown"))
                        builder.record("RIFF.INFO", name, "RIFF.INFO.{}".format(info_id), value, category, tag_id=info_id, offset=payload.base + inner + 8, length=info_length)
                        builder.node(info_id, "info", payload.base + inner, 8 + info_padded, node_id)
                        inner += 8 + info_padded
                position += 8 + padded
            if data_length is not None and byte_rate:
                builder.record("WAVE", "Duration", "WAVE.Duration", round(data_length / byte_rate, 6), "audio", description="Duration derived from data length and byte rate")
        except (BoundsError, LimitExceeded) as exc:
            builder.warn("riff.malformed", "RIFF parsing stopped safely: {}".format(str(exc)), reader.base + min(position, reader.size))
        return builder.output

