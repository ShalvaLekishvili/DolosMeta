"""Secure, namespace-preserving XMP and small XML metadata parsing."""

from __future__ import annotations

import re
from typing import Dict, Optional

from defusedxml import ElementTree

from ..binary import BinaryReader
from ..errors import LimitExceeded, MalformedFile
from .base import OutputBuilder, ParseContext, ParserOutput


NAMESPACE_PREFIXES = {
    "http://purl.org/dc/elements/1.1/": "dc",
    "http://ns.adobe.com/xap/1.0/": "xmp",
    "http://ns.adobe.com/photoshop/1.0/": "photoshop",
    "http://ns.adobe.com/exif/1.0/": "exif",
    "http://ns.adobe.com/tiff/1.0/": "tiff",
    "http://ns.adobe.com/exif/1.0/aux/": "aux",
    "http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/": "iptc",
    "http://ns.adobe.com/camera-raw-settings/1.0/": "crs",
    "http://ns.microsoft.com/photo/1.0/": "MicrosoftPhoto",
}


def _split(tag: str) -> tuple:
    if tag.startswith("{") and "}" in tag:
        uri, local = tag[1:].split("}", 1)
        return uri, local
    return "", tag


def _prefix(uri: str) -> str:
    if not uri:
        return "xmp"
    return NAMESPACE_PREFIXES.get(uri, "ns_" + re.sub(r"[^a-zA-Z0-9]", "", uri)[-12:])


def parse_xmp_bytes(
    data: bytes,
    context: ParseContext,
    absolute_offset: int = 0,
) -> ParserOutput:
    builder = OutputBuilder("xmp", context.budget)
    if len(data) > context.budget.settings.max_metadata_block_bytes:
        builder.warn("xmp.too_large", "XMP block exceeded the configured metadata limit", absolute_offset)
        return builder.output
    upper = data[:4096].upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        builder.warn("xml.forbidden_declaration", "DTD/entity declarations are not permitted", absolute_offset)
        return builder.output
    try:
        root = ElementTree.fromstring(data)
    except Exception as exc:  # DefusedXmlException and parse errors are safe to surface
        builder.warn("xmp.malformed", "XMP XML could not be parsed: {}".format(type(exc).__name__), absolute_offset)
        return builder.output
    root_id = builder.node("XMP", "metadata", absolute_offset, len(data), details={"root": root.tag})
    try:
        for element in root.iter():
            uri, local = _split(element.tag)
            namespace = _prefix(uri)
            text = (element.text or "").strip()
            if text and len(list(element)) == 0:
                builder.record(
                    namespace,
                    local,
                    "{}.{}".format(namespace, local),
                    text[:16_384],
                    category="unknown",
                    offset=absolute_offset,
                    length=len(data),
                )
            for attr_name, attr_value in element.attrib.items():
                attr_uri, attr_local = _split(attr_name)
                attr_namespace = _prefix(attr_uri or uri)
                builder.record(
                    attr_namespace,
                    attr_local,
                    "{}.{}".format(attr_namespace, attr_local),
                    attr_value[:16_384],
                    category="unknown",
                    offset=absolute_offset,
                    length=len(data),
                )
    except LimitExceeded:
        builder.warn("xmp.truncated", "XMP records were truncated by the metadata record limit")
    return builder.output


def parse_xmp_region(reader: BinaryReader, context: ParseContext) -> ParserOutput:
    maximum = min(reader.size, context.budget.settings.max_metadata_block_bytes)
    return parse_xmp_bytes(reader.read(0, maximum), context, reader.base)

