"""Explicit parser allow-list and capability inventory."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from .parsers.base import MetadataParser, ParserDescriptor


class ParserRegistry:
    def __init__(self) -> None:
        self._by_format: Dict[str, MetadataParser] = {}
        self._parsers: List[MetadataParser] = []

    def register(self, parser: MetadataParser) -> None:
        if parser in self._parsers:
            return
        self._parsers.append(parser)
        for file_format in parser.descriptor.formats:
            key = file_format.upper()
            if key in self._by_format:
                raise ValueError("parser already registered for {}".format(key))
            self._by_format[key] = parser

    def get(self, file_format: str) -> Optional[MetadataParser]:
        return self._by_format.get(file_format.upper())

    def descriptors(self) -> Iterable[ParserDescriptor]:
        return (parser.descriptor for parser in self._parsers)

