"""Parser contract and bounded output helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence
from uuid import uuid4

from dolosmeta.models import Artifact, DetectionResult, MetadataRecord, ParserWarning, StructureNode

from ..binary import BinaryReader
from ..budgets import AnalysisBudget


@dataclass(frozen=True)
class ParserDescriptor:
    name: str
    version: str
    formats: Sequence[str]
    capability: str
    description: str


@dataclass
class ParserOutput:
    records: List[MetadataRecord] = field(default_factory=list)
    structure: List[StructureNode] = field(default_factory=list)
    warnings: List[ParserWarning] = field(default_factory=list)
    artifacts: List[Artifact] = field(default_factory=list)
    format_override: Optional[str] = None
    mime_override: Optional[str] = None

    def extend(self, other: "ParserOutput") -> None:
        self.records.extend(other.records)
        self.structure.extend(other.structure)
        self.warnings.extend(other.warnings)
        self.artifacts.extend(other.artifacts)
        self.format_override = other.format_override or self.format_override
        self.mime_override = other.mime_override or self.mime_override


@dataclass
class ParseContext:
    budget: AnalysisBudget
    detection: DetectionResult


class MetadataParser(Protocol):
    descriptor: ParserDescriptor

    def parse(self, reader: BinaryReader, context: ParseContext) -> ParserOutput:
        ...


def safe_text(data: bytes, encoding: str = "utf-8", maximum: int = 16_384) -> str:
    clipped = data[:maximum]
    return clipped.rstrip(b"\x00").decode(encoding, errors="replace").replace("\x00", "")


def safe_value(value: Any, binary_preview: int = 64) -> Any:
    if isinstance(value, bytes):
        return {"type": "binary", "length": len(value), "preview_hex": value[:binary_preview].hex()}
    if isinstance(value, tuple):
        return [safe_value(item, binary_preview) for item in value]
    if isinstance(value, list):
        return [safe_value(item, binary_preview) for item in value]
    if isinstance(value, dict):
        return {str(key): safe_value(item, binary_preview) for key, item in value.items()}
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return str(value)
    return value


class OutputBuilder:
    def __init__(self, parser: str, budget: AnalysisBudget) -> None:
        self.parser = parser
        self.budget = budget
        self.output = ParserOutput()
        self._id_prefix = "{}:{}".format(parser, uuid4().hex[:10])
        self._record_number = 0
        self._node_number = 0
        self._artifact_number = 0

    def record(
        self,
        namespace: str,
        name: str,
        path: str,
        value: Any,
        category: str = "unknown",
        tag_id: Optional[str] = None,
        description: Optional[str] = None,
        offset: Optional[int] = None,
        length: Optional[int] = None,
        display_value: Optional[str] = None,
    ) -> MetadataRecord:
        self.budget.claim_records()
        self._record_number += 1
        item = MetadataRecord(
            id="{}:r{}".format(self._id_prefix, self._record_number),
            namespace=namespace,
            name=name,
            path=path,
            value=safe_value(value),
            display_value=display_value,
            tag_id=tag_id,
            category=category,
            description=description,
            offset=offset,
            length=length,
            parser=self.parser,
        )
        self.output.records.append(item)
        return item

    def node(
        self,
        label: str,
        kind: str,
        offset: int,
        length: int,
        parent_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        self.budget.claim_nodes()
        self._node_number += 1
        node_id = "{}:n{}".format(self._id_prefix, self._node_number)
        self.output.structure.append(
            StructureNode(
                id=node_id,
                parent_id=parent_id,
                label=label,
                kind=kind,
                offset=max(0, offset),
                length=max(0, length),
                details=safe_value(details or {}),
            )
        )
        return node_id

    def warn(self, code: str, message: str, offset: Optional[int] = None) -> None:
        self.output.warnings.append(
            ParserWarning(code=code, message=message, parser=self.parser, offset=offset)
        )

    def artifact(
        self,
        name: str,
        media_type: str,
        offset: int,
        length: int,
        description: Optional[str] = None,
    ) -> None:
        self._artifact_number += 1
        self.output.artifacts.append(
            Artifact(
                id="{}:a{}".format(self._id_prefix, self._artifact_number),
                name=name,
                media_type=media_type,
                offset=offset,
                length=length,
                description=description,
            )
        )
