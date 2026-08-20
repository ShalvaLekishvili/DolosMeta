"""Safe archive inventory and OOXML property inspection without extraction."""

from __future__ import annotations

import re
import stat
import zipfile
from datetime import datetime
from pathlib import PurePosixPath
from typing import Dict, List, Optional, Tuple

from defusedxml import ElementTree

from ..binary import BinaryReader
from ..errors import BoundsError, LimitExceeded
from .base import OutputBuilder, ParseContext, ParserDescriptor, ParserOutput, safe_text


CORE_PROPERTIES = {
    "title": ("Title", "document"),
    "subject": ("Subject", "document"),
    "creator": ("Creator", "author"),
    "keywords": ("Keywords", "document"),
    "description": ("Description", "document"),
    "lastModifiedBy": ("LastModifiedBy", "author"),
    "revision": ("Revision", "document"),
    "created": ("Created", "time"),
    "modified": ("Modified", "time"),
    "category": ("Category", "document"),
    "contentStatus": ("ContentStatus", "document"),
}

APP_PROPERTIES = {
    "Application": ("Application", "software"),
    "AppVersion": ("ApplicationVersion", "software"),
    "Company": ("Company", "author"),
    "Manager": ("Manager", "author"),
    "Template": ("Template", "document"),
    "TotalTime": ("TotalEditingTime", "document"),
    "Pages": ("Pages", "document"),
    "Words": ("Words", "document"),
    "Characters": ("Characters", "document"),
    "Slides": ("Slides", "document"),
    "HiddenSlides": ("HiddenSlides", "document"),
}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _unsafe_name(name: str) -> bool:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    return (
        normalized.startswith("/")
        or bool(re.match(r"^[a-zA-Z]:", normalized))
        or ".." in path.parts
    )


def _read_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    context: ParseContext,
    builder: OutputBuilder,
) -> Optional[bytes]:
    maximum = context.budget.settings.max_metadata_block_bytes
    if info.file_size > maximum:
        builder.warn("archive.member_too_large", "{} exceeds the metadata member limit".format(info.filename))
        return None
    try:
        with archive.open(info, "r") as member:
            data = member.read(maximum + 1)
        if len(data) > maximum:
            builder.warn("archive.member_too_large", "{} expanded beyond the metadata member limit".format(info.filename))
            return None
        context.budget.claim_decompressed(len(data))
        return data
    except (OSError, RuntimeError, zipfile.BadZipFile, LimitExceeded) as exc:
        builder.warn("archive.member_error", "{} could not be inspected: {}".format(info.filename, type(exc).__name__))
        return None


def _parse_properties(data: bytes, namespace: str, mapping: Dict[str, Tuple[str, str]], builder: OutputBuilder) -> None:
    if b"<!DOCTYPE" in data[:4096].upper() or b"<!ENTITY" in data[:4096].upper():
        builder.warn("xml.forbidden_declaration", "DTD/entity declarations are not permitted in Office XML")
        return
    try:
        root = ElementTree.fromstring(data)
    except Exception as exc:
        builder.warn("ooxml.malformed_xml", "Office property XML is malformed: {}".format(type(exc).__name__))
        return
    for element in root.iter():
        local = _local(element.tag)
        definition = mapping.get(local)
        if definition and element.text is not None:
            name, category = definition
            builder.record(namespace, name, "{}.{}".format(namespace, name), element.text.strip()[:16_384], category)


def _parse_custom(data: bytes, builder: OutputBuilder) -> None:
    if b"<!DOCTYPE" in data[:4096].upper() or b"<!ENTITY" in data[:4096].upper():
        builder.warn("xml.forbidden_declaration", "DTD/entity declarations are not permitted in Office XML")
        return
    try:
        root = ElementTree.fromstring(data)
    except Exception as exc:
        builder.warn("ooxml.malformed_xml", "Custom property XML is malformed: {}".format(type(exc).__name__))
        return
    for prop in root:
        name = prop.attrib.get("name", "CustomProperty")[:256]
        value_node = next(iter(prop), None)
        value = (value_node.text or "").strip()[:16_384] if value_node is not None else ""
        builder.record("Office.Custom", name, "Office.Custom.{}".format(name), value, "document")


def _parse_relationships(data: bytes, source_name: str, builder: OutputBuilder) -> None:
    if b"<!DOCTYPE" in data[:4096].upper() or b"<!ENTITY" in data[:4096].upper():
        builder.warn("xml.forbidden_declaration", "DTD/entity declarations are not permitted in relationships XML")
        return
    try:
        root = ElementTree.fromstring(data)
    except Exception as exc:
        builder.warn("ooxml.malformed_relationships", "Relationships XML is malformed: {}".format(type(exc).__name__))
        return
    for relation in root.iter():
        if _local(relation.tag) != "Relationship":
            continue
        target = relation.attrib.get("Target", "")[:4096]
        relation_type = relation.attrib.get("Type", "").rsplit("/", 1)[-1][:256]
        external = relation.attrib.get("TargetMode", "").lower() == "external"
        if external:
            builder.record(
                "Office.Relationships",
                "ExternalRelationship",
                "Office.Relationships.ExternalRelationship",
                {"source": source_name, "type": relation_type, "target": target},
                "security",
            )


class ArchiveParser:
    descriptor = ParserDescriptor(
        name="Archive/OOXML Parser",
        version="1.0",
        formats=("ZIP", "TAR", "GZIP"),
        capability="good",
        description="Bounded archive inventory and OOXML metadata/relationship inspection",
    )

    def parse(self, reader: BinaryReader, context: ParseContext) -> ParserOutput:
        if context.detection.format == "ZIP":
            return self._zip(reader, context)
        if context.detection.format == "TAR":
            return self._tar(reader, context)
        return self._gzip(reader, context)

    def _zip(self, reader: BinaryReader, context: ParseContext) -> ParserOutput:
        builder = OutputBuilder("archive-ooxml", context.budget)
        root_id = builder.node("ZIP", "archive", reader.base, reader.size)
        try:
            with zipfile.ZipFile(reader.source.path, "r") as archive:
                infos = archive.infolist()
                if len(infos) > context.budget.settings.max_archive_entries:
                    builder.warn("archive.entry_limit", "Archive entry inventory was truncated")
                    infos = infos[: context.budget.settings.max_archive_entries]
                    context.budget.note("archive entry limit reached")
                names = {info.filename for info in infos}
                lowered = {name.lower() for name in names}
                ooxml_format = None
                macro = any(name.endswith("vbaproject.bin") for name in lowered)
                if "word/document.xml" in lowered:
                    ooxml_format = "DOCM" if macro else "DOCX"
                elif "xl/workbook.xml" in lowered:
                    ooxml_format = "XLSM" if macro else "XLSX"
                elif "ppt/presentation.xml" in lowered:
                    ooxml_format = "PPTM" if macro else "PPTX"
                if ooxml_format:
                    builder.output.format_override = ooxml_format
                    builder.output.mime_override = {
                        "DOCX": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "XLSX": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "PPTX": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        "DOCM": "application/vnd.ms-word.document.macroenabled.12",
                        "XLSM": "application/vnd.ms-excel.sheet.macroenabled.12",
                        "PPTM": "application/vnd.ms-powerpoint.presentation.macroenabled.12",
                    }[ooxml_format]
                    builder.record("Office", "Format", "Office.Format", ooxml_format, "document")
                total_uncompressed = 0
                total_compressed = 0
                directories = 0
                nested = 0
                for info in infos:
                    context.budget.check()
                    total_uncompressed += max(0, info.file_size)
                    total_compressed += max(0, info.compress_size)
                    directories += int(info.is_dir())
                    suffix = PurePosixPath(info.filename.lower()).suffix
                    nested += int(suffix in {".zip", ".tar", ".gz", ".rar", ".7z"})
                    mode = (info.external_attr >> 16) & 0xFFFF
                    unsafe = _unsafe_name(info.filename)
                    symlink = stat.S_IFMT(mode) == stat.S_IFLNK
                    if unsafe:
                        builder.warn("archive.path_traversal", "Unsafe archive path: {}".format(info.filename))
                    if symlink:
                        builder.warn("archive.symlink", "Archive contains a symbolic link: {}".format(info.filename))
                    ratio = info.file_size / max(1, info.compress_size)
                    if ratio > 1000 and info.file_size > 10 * 1024 * 1024:
                        builder.warn("archive.high_ratio", "Potential decompression bomb entry: {}".format(info.filename))
                    builder.node(
                        info.filename[:4096],
                        "directory" if info.is_dir() else "entry",
                        reader.base + max(0, info.header_offset),
                        max(0, info.compress_size),
                        root_id,
                        {"compressed_size": info.compress_size, "uncompressed_size": info.file_size, "timestamp": "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}".format(*info.date_time)},
                    )
                for name, value in (
                    ("FileCount", len(infos) - directories),
                    ("DirectoryCount", directories),
                    ("CompressedSize", total_compressed),
                    ("UncompressedSize", total_uncompressed),
                    ("CompressionRatio", round(total_uncompressed / max(1, total_compressed), 3)),
                    ("NestedArchiveCount", nested),
                ):
                    builder.record("Archive", name, "Archive.{}".format(name), value, "archive")
                if macro:
                    builder.record("Office.Security", "MacrosPresent", "Office.Security.MacrosPresent", True, "security")
                embedded = [name for name in names if "/embeddings/" in name.lower()]
                if embedded:
                    builder.record("Office.Security", "EmbeddedObjectCount", "Office.Security.EmbeddedObjectCount", len(embedded), "security")
                by_lower = {info.filename.lower(): info for info in infos}
                for member_name, namespace, mapping in (
                    ("docprops/core.xml", "Office.Core", CORE_PROPERTIES),
                    ("docprops/app.xml", "Office.App", APP_PROPERTIES),
                ):
                    info = by_lower.get(member_name)
                    if info:
                        data = _read_member(archive, info, context, builder)
                        if data is not None:
                            _parse_properties(data, namespace, mapping, builder)
                custom = by_lower.get("docprops/custom.xml")
                if custom:
                    data = _read_member(archive, custom, context, builder)
                    if data is not None:
                        _parse_custom(data, builder)
                relationship_infos = [info for info in infos if info.filename.lower().endswith(".rels")]
                for info in relationship_infos[:256]:
                    data = _read_member(archive, info, context, builder)
                    if data is not None:
                        _parse_relationships(data, info.filename, builder)
        except (zipfile.BadZipFile, OSError, EOFError, LimitExceeded) as exc:
            builder.warn("archive.malformed", "ZIP inspection stopped safely: {}".format(type(exc).__name__), reader.base)
        return builder.output

    def _tar(self, reader: BinaryReader, context: ParseContext) -> ParserOutput:
        builder = OutputBuilder("tar", context.budget)
        root_id = builder.node("TAR", "archive", reader.base, reader.size)
        position = 0
        entries = 0
        total_size = 0
        try:
            while position <= reader.size - 512 and entries < context.budget.settings.max_archive_entries:
                context.budget.check()
                header = reader.read(position, 512)
                if header == b"\x00" * 512:
                    break
                name = safe_text(header[0:100], "utf-8", 100)
                prefix = safe_text(header[345:500], "utf-8", 155)
                if prefix:
                    name = prefix + "/" + name
                size_text = header[124:136].rstrip(b"\x00 ") or b"0"
                try:
                    entry_size = int(size_text, 8)
                except ValueError:
                    builder.warn("tar.invalid_size", "TAR entry has an invalid size", reader.base + position)
                    break
                type_flag = header[156:157]
                if entry_size < 0 or entry_size > reader.size - position - 512:
                    builder.warn("tar.invalid_span", "TAR entry extends outside the file", reader.base + position)
                    break
                unsafe = _unsafe_name(name)
                if unsafe:
                    builder.warn("archive.path_traversal", "Unsafe archive path: {}".format(name))
                if type_flag in {b"1", b"2"}:
                    builder.warn("archive.link", "Archive link entry detected: {}".format(name))
                builder.node(name[:4096], "entry", reader.base + position, 512 + entry_size, root_id, {"size": entry_size, "type": safe_text(type_flag, "ascii", 1)})
                entries += 1
                total_size += entry_size
                position += 512 + ((entry_size + 511) // 512) * 512
            if entries >= context.budget.settings.max_archive_entries:
                context.budget.note("archive entry limit reached")
                builder.warn("archive.entry_limit", "TAR entry inventory was truncated")
            builder.record("Archive", "FileCount", "Archive.FileCount", entries, "archive")
            builder.record("Archive", "UncompressedSize", "Archive.UncompressedSize", total_size, "archive")
        except (BoundsError, LimitExceeded) as exc:
            builder.warn("tar.malformed", "TAR inspection stopped safely: {}".format(str(exc)), reader.base + min(position, reader.size))
        return builder.output

    def _gzip(self, reader: BinaryReader, context: ParseContext) -> ParserOutput:
        builder = OutputBuilder("gzip", context.budget)
        root_id = builder.node("GZIP", "archive", reader.base, reader.size)
        if reader.size < 10 or reader.read(0, 3) != b"\x1f\x8b\x08":
            builder.warn("gzip.signature", "GZIP header is invalid", reader.base)
            return builder.output
        flags = reader.u8(3)
        mtime = reader.u32(4, "<")
        builder.record("GZIP", "Flags", "GZIP.Flags", flags, "archive", offset=reader.base + 3, length=1)
        builder.record("GZIP", "ModificationTimeUnix", "GZIP.ModificationTimeUnix", mtime, "time", offset=reader.base + 4, length=4)
        position = 10
        try:
            if flags & 0x04:
                extra_length = reader.u16(position, "<")
                position += 2 + extra_length
            if flags & 0x08:
                filename = reader.cstring(position, min(4096, reader.size - position), "latin-1")
                builder.record("GZIP", "OriginalFilename", "GZIP.OriginalFilename", filename, "archive", offset=reader.base + position)
            if reader.size >= 8:
                builder.record("GZIP", "UncompressedSizeModulo32", "GZIP.UncompressedSizeModulo32", reader.u32(reader.size - 4, "<"), "archive", offset=reader.base + reader.size - 4, length=4)
        except BoundsError as exc:
            builder.warn("gzip.truncated", "GZIP optional header is truncated: {}".format(str(exc)), reader.base + min(position, reader.size))
        return builder.output

