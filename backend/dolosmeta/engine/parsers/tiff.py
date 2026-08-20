"""Native TIFF/EXIF IFD reader with strict relative-offset bounds."""

from __future__ import annotations

import math
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..binary import BinaryReader
from ..errors import BoundsError, LimitExceeded, MalformedFile
from .base import OutputBuilder, ParseContext, ParserDescriptor, ParserOutput, safe_text


TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8, 13: 4}

IMAGE_TAGS = {
    0x0100: ("ImageWidth", "media", "Image width in pixels"),
    0x0101: ("ImageLength", "media", "Image height in pixels"),
    0x0102: ("BitsPerSample", "media", "Bits per image component"),
    0x0103: ("Compression", "media", "TIFF compression method"),
    0x0106: ("PhotometricInterpretation", "media", "Pixel color interpretation"),
    0x010E: ("ImageDescription", "document", "Image description"),
    0x010F: ("Make", "camera", "Camera manufacturer"),
    0x0110: ("Model", "camera", "Camera model"),
    0x0112: ("Orientation", "media", "Stored image orientation"),
    0x011A: ("XResolution", "media", "Horizontal resolution"),
    0x011B: ("YResolution", "media", "Vertical resolution"),
    0x0128: ("ResolutionUnit", "media", "Resolution unit"),
    0x0131: ("Software", "software", "Software that wrote the metadata"),
    0x0132: ("DateTime", "time", "File change date reported by TIFF metadata"),
    0x013B: ("Artist", "author", "Image creator"),
    0x8298: ("Copyright", "author", "Copyright statement"),
    0x8769: ("ExifIFDPointer", "structure", "Offset of the Exif IFD"),
    0x8825: ("GPSInfoIFDPointer", "structure", "Offset of the GPS IFD"),
    0xA005: ("InteroperabilityIFDPointer", "structure", "Offset of the interoperability IFD"),
    0x014A: ("SubIFDs", "structure", "Offsets of child IFDs"),
    0x0201: ("JPEGInterchangeFormat", "structure", "Embedded thumbnail offset"),
    0x0202: ("JPEGInterchangeFormatLength", "structure", "Embedded thumbnail length"),
}

EXIF_TAGS = {
    0x829A: ("ExposureTime", "camera", "Exposure duration"),
    0x829D: ("FNumber", "camera", "Lens aperture f-number"),
    0x8822: ("ExposureProgram", "camera", "Camera exposure program"),
    0x8827: ("ISO", "camera", "ISO speed rating"),
    0x8830: ("SensitivityType", "camera", "Sensitivity interpretation"),
    0x9000: ("ExifVersion", "media", "EXIF version"),
    0x9003: ("DateTimeOriginal", "time", "Capture time reported by the device"),
    0x9004: ("DateTimeDigitized", "time", "Digitization time reported by the device"),
    0x9010: ("OffsetTime", "time", "UTC offset for DateTime"),
    0x9011: ("OffsetTimeOriginal", "time", "UTC offset for original capture time"),
    0x9012: ("OffsetTimeDigitized", "time", "UTC offset for digitized time"),
    0x9201: ("ShutterSpeedValue", "camera", "APEX shutter speed"),
    0x9202: ("ApertureValue", "camera", "APEX aperture"),
    0x9203: ("BrightnessValue", "camera", "APEX brightness"),
    0x9204: ("ExposureBiasValue", "camera", "Exposure compensation"),
    0x9205: ("MaxApertureValue", "camera", "Maximum aperture"),
    0x9207: ("MeteringMode", "camera", "Metering mode"),
    0x9208: ("LightSource", "camera", "Light source"),
    0x9209: ("Flash", "camera", "Flash status"),
    0x920A: ("FocalLength", "lens", "Lens focal length"),
    0x9286: ("UserComment", "document", "EXIF user comment"),
    0xA001: ("ColorSpace", "media", "Image color space"),
    0xA002: ("PixelXDimension", "media", "Image width reported by EXIF"),
    0xA003: ("PixelYDimension", "media", "Image height reported by EXIF"),
    0xA402: ("ExposureMode", "camera", "Exposure mode"),
    0xA403: ("WhiteBalance", "camera", "White balance mode"),
    0xA404: ("DigitalZoomRatio", "camera", "Digital zoom ratio"),
    0xA405: ("FocalLengthIn35mmFilm", "lens", "35 mm-equivalent focal length"),
    0xA406: ("SceneCaptureType", "camera", "Scene capture type"),
    0xA430: ("CameraOwnerName", "author", "Camera owner name"),
    0xA431: ("BodySerialNumber", "camera", "Camera body serial number"),
    0xA432: ("LensSpecification", "lens", "Lens focal/aperture specification"),
    0xA433: ("LensMake", "lens", "Lens manufacturer"),
    0xA434: ("LensModel", "lens", "Lens model"),
    0xA435: ("LensSerialNumber", "lens", "Lens serial number"),
}

GPS_TAGS = {
    0x0000: ("GPSVersionID", "location", "GPS tag version"),
    0x0001: ("GPSLatitudeRef", "location", "Latitude hemisphere"),
    0x0002: ("GPSLatitude", "location", "Latitude in degrees, minutes, seconds"),
    0x0003: ("GPSLongitudeRef", "location", "Longitude hemisphere"),
    0x0004: ("GPSLongitude", "location", "Longitude in degrees, minutes, seconds"),
    0x0005: ("GPSAltitudeRef", "location", "Altitude reference"),
    0x0006: ("GPSAltitude", "location", "Altitude"),
    0x0007: ("GPSTimeStamp", "time", "GPS time"),
    0x000C: ("GPSSpeedRef", "location", "GPS speed unit"),
    0x000D: ("GPSSpeed", "location", "GPS speed"),
    0x0010: ("GPSImgDirectionRef", "location", "Image direction reference"),
    0x0011: ("GPSImgDirection", "location", "Image direction"),
    0x0013: ("GPSDestLatitudeRef", "location", "Destination latitude hemisphere"),
    0x0014: ("GPSDestLatitude", "location", "Destination latitude"),
    0x0015: ("GPSDestLongitudeRef", "location", "Destination longitude hemisphere"),
    0x0016: ("GPSDestLongitude", "location", "Destination longitude"),
    0x001D: ("GPSDateStamp", "time", "GPS date"),
}


def _tag_definition(ifd_name: str, tag: int) -> Tuple[str, str, str]:
    database = GPS_TAGS if ifd_name == "GPSIFD" else (EXIF_TAGS if ifd_name in {"ExifIFD", "InteropIFD"} else IMAGE_TAGS)
    return database.get(tag, ("UnknownTag0x{:04X}".format(tag), "unknown", "Unrecognized TIFF/EXIF tag; raw value preserved"))


def _scalar_or_list(values: List[Any]) -> Any:
    return values[0] if len(values) == 1 else values


def _decode_value(reader: BinaryReader, field_type: int, count: int, data_offset: int, total: int) -> Any:
    data = reader.read(data_offset, total)
    endian = "little" if reader.endian == "<" else "big"
    if field_type == 2:
        return safe_text(data, "ascii")
    if field_type in {1, 6}:
        values = list(data)
        if field_type == 6:
            values = [item - 256 if item >= 128 else item for item in values]
        return _scalar_or_list(values)
    if field_type == 7:
        # Four-byte EXIF version values are useful as ASCII; arbitrary data stays binary.
        if all(byte == 0 or 32 <= byte <= 126 for byte in data):
            return safe_text(data, "ascii")
        return data
    fmt = {3: "H", 4: "I", 8: "h", 9: "i", 11: "f", 12: "d", 13: "I"}.get(field_type)
    if fmt:
        values = [reader.unpack(fmt, data_offset + index * TYPE_SIZES[field_type])[0] for index in range(count)]
        return _scalar_or_list(values)
    if field_type in {5, 10}:
        signed = field_type == 10
        values = []
        for index in range(count):
            position = data_offset + index * 8
            numerator = int.from_bytes(reader.read(position, 4), endian, signed=signed)
            denominator = int.from_bytes(reader.read(position + 4, 4), endian, signed=signed)
            values.append(None if denominator == 0 else numerator / denominator)
        return _scalar_or_list(values)
    return data


def _coordinates(value: Any, reference: Any) -> Optional[float]:
    if not isinstance(value, list) or len(value) < 3 or any(item is None for item in value[:3]):
        return None
    try:
        decimal = float(value[0]) + float(value[1]) / 60.0 + float(value[2]) / 3600.0
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(decimal):
        return None
    if str(reference).strip().upper() in {"S", "W"}:
        decimal *= -1
    return round(decimal, 8)


def parse_tiff(reader: BinaryReader, context: ParseContext) -> ParserOutput:
    builder = OutputBuilder("tiff-exif", context.budget)
    if reader.size < 8:
        builder.warn("tiff.truncated", "TIFF header is truncated", reader.base)
        return builder.output
    marker = reader.read(0, 2)
    if marker == b"II":
        endian = "<"
    elif marker == b"MM":
        endian = ">"
    else:
        builder.warn("tiff.byte_order", "Invalid TIFF byte-order marker", reader.base)
        return builder.output
    reader = BinaryReader(reader.source, reader.base, reader.size, endian)
    try:
        if reader.u16(2) not in {42, 43}:
            raise MalformedFile("unsupported TIFF magic")
        if reader.u16(2) == 43:
            builder.warn("tiff.bigtiff", "BigTIFF is detected but is not parsed by this version", reader.base)
            return builder.output
        first_ifd = reader.u32(4)
        root_id = builder.node("TIFF", "container", reader.base, reader.size, details={"byte_order": "little" if endian == "<" else "big"})
        queue = [(first_ifd, "IFD0", root_id, 0)]
        visited = set()
        values: Dict[Tuple[str, int], Any] = {}
        thumbnail_offset = None
        thumbnail_length = None
        while queue:
            ifd_offset, ifd_name, parent_id, depth = queue.pop(0)
            context.budget.depth(depth)
            if ifd_offset in visited:
                builder.warn("tiff.ifd_cycle", "Repeated IFD offset was ignored", reader.base + ifd_offset)
                continue
            visited.add(ifd_offset)
            if ifd_offset > reader.size - 2:
                builder.warn("tiff.invalid_ifd_offset", "IFD offset is outside the TIFF block", reader.base + min(ifd_offset, reader.size))
                continue
            count = reader.u16(ifd_offset)
            if count > 4096:
                builder.warn("tiff.excessive_entries", "IFD entry count exceeds the safety limit", reader.base + ifd_offset)
                count = 4096
            table_bytes = 2 + count * 12 + 4
            if table_bytes > reader.size - ifd_offset:
                possible = max(0, (reader.size - ifd_offset - 6) // 12)
                builder.warn("tiff.truncated_ifd", "IFD table is truncated", reader.base + ifd_offset)
                count = min(count, possible)
            ifd_id = builder.node(ifd_name, "ifd", reader.base + ifd_offset, min(table_bytes, reader.size - ifd_offset), parent_id, {"entries": count})
            pointers: List[Tuple[int, str]] = []
            for index in range(count):
                context.budget.check()
                entry = ifd_offset + 2 + index * 12
                try:
                    tag = reader.u16(entry)
                    field_type = reader.u16(entry + 2)
                    value_count = reader.u32(entry + 4)
                    unit = TYPE_SIZES.get(field_type)
                    if unit is None:
                        builder.warn("tiff.unknown_type", "Unknown TIFF field type {}".format(field_type), reader.base + entry)
                        continue
                    if value_count > context.budget.settings.max_metadata_block_bytes // max(1, unit):
                        builder.warn("tiff.value_too_large", "Declared TIFF value is too large", reader.base + entry)
                        continue
                    total = value_count * unit
                    if total > context.budget.settings.max_metadata_block_bytes:
                        builder.warn("tiff.value_too_large", "TIFF value exceeds metadata limit", reader.base + entry)
                        continue
                    data_offset = entry + 8 if total <= 4 else reader.u32(entry + 8)
                    value = _decode_value(reader, field_type, value_count, data_offset, total)
                    name, category, description = _tag_definition(ifd_name, tag)
                    namespace = "Exif.GPSInfo" if ifd_name == "GPSIFD" else ("Exif.Photo" if ifd_name in {"ExifIFD", "InteropIFD"} else "Exif.Image")
                    record = builder.record(
                        namespace,
                        name,
                        "{}.{}".format(namespace, name),
                        value,
                        category=category,
                        tag_id="0x{:04X}".format(tag),
                        description=description,
                        offset=reader.base + data_offset,
                        length=total,
                    )
                    values[(ifd_name, tag)] = record.value
                    pointer_values = value if isinstance(value, list) else [value]
                    if tag == 0x8769:
                        pointers.extend((int(item), "ExifIFD") for item in pointer_values if isinstance(item, int))
                    elif tag == 0x8825:
                        pointers.extend((int(item), "GPSIFD") for item in pointer_values if isinstance(item, int))
                    elif tag == 0xA005:
                        pointers.extend((int(item), "InteropIFD") for item in pointer_values if isinstance(item, int))
                    elif tag == 0x014A:
                        pointers.extend((int(item), "SubIFD") for item in pointer_values if isinstance(item, int))
                    elif ifd_name == "IFD1" and tag == 0x0201 and isinstance(value, int):
                        thumbnail_offset = value
                    elif ifd_name == "IFD1" and tag == 0x0202 and isinstance(value, int):
                        thumbnail_length = value
                except (BoundsError, struct.error, ValueError) as exc:
                    builder.warn("tiff.invalid_entry", "TIFF entry could not be decoded: {}".format(type(exc).__name__), reader.base + entry)
            for pointer, pointer_name in pointers:
                if 0 < pointer < reader.size:
                    queue.append((pointer, pointer_name, ifd_id, depth + 1))
                else:
                    builder.warn("tiff.invalid_pointer", "{} points outside the TIFF block".format(pointer_name), reader.base + min(max(pointer, 0), reader.size))
            next_pos = ifd_offset + 2 + count * 12
            if next_pos <= reader.size - 4:
                next_ifd = reader.u32(next_pos)
                if next_ifd and ifd_name == "IFD0":
                    queue.append((next_ifd, "IFD1", ifd_id, depth + 1))
        latitude = _coordinates(values.get(("GPSIFD", 0x0002)), values.get(("GPSIFD", 0x0001)))
        longitude = _coordinates(values.get(("GPSIFD", 0x0004)), values.get(("GPSIFD", 0x0003)))
        if latitude is not None and longitude is not None and -90 <= latitude <= 90 and -180 <= longitude <= 180:
            builder.record("Composite", "GPSLatitude", "Composite.GPSLatitude", latitude, "location", description="Decimal latitude derived from EXIF GPS rationals")
            builder.record("Composite", "GPSLongitude", "Composite.GPSLongitude", longitude, "location", description="Decimal longitude derived from EXIF GPS rationals")
        if thumbnail_offset is not None and thumbnail_length is not None:
            if thumbnail_length > 0 and thumbnail_offset <= reader.size and thumbnail_length <= reader.size - thumbnail_offset:
                builder.artifact("embedded-thumbnail.jpg", "image/jpeg", reader.base + thumbnail_offset, thumbnail_length, "EXIF IFD1 embedded thumbnail")
            else:
                builder.warn("tiff.invalid_thumbnail", "Embedded thumbnail span is outside the EXIF block")
    except (BoundsError, MalformedFile, LimitExceeded, struct.error) as exc:
        builder.warn("tiff.malformed", "TIFF metadata is malformed: {}".format(str(exc) or type(exc).__name__), reader.base)
    return builder.output


class TIFFParser:
    descriptor = ParserDescriptor(
        name="TIFF/EXIF Parser",
        version="1.0",
        formats=("TIFF",),
        capability="full",
        description="Native TIFF IFD and EXIF metadata parser",
    )

    def parse(self, reader: BinaryReader, context: ParseContext) -> ParserOutput:
        return parse_tiff(reader, context)

