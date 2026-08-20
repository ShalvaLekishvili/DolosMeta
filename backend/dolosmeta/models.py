"""Versioned public models shared by the engine, API, exporters, and CLI."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EvidenceKind(str, Enum):
    OBSERVED = "observed"
    DERIVED = "derived"
    INFERENCE = "inference"


class FileInfo(StrictModel):
    name: str
    size: int = Field(ge=0)
    extension: str = ""
    declared_mime: Optional[str] = None
    mime: str = "application/octet-stream"
    detected_format: str = "Unknown"
    signature: Optional[str] = None
    signature_match: Optional[bool] = None
    magic_hex: str = ""
    binary: bool = True
    upload_session_created: datetime


class Hashes(StrictModel):
    sha256: str
    sha512: str
    sha1: str
    md5: str


class Metrics(StrictModel):
    entropy: float = Field(ge=0.0, le=8.0)
    entropy_level: str


class BinaryValue(StrictModel):
    type: str = "binary"
    length: int = Field(ge=0)
    preview_hex: str = ""
    base64: Optional[str] = None


class MetadataRecord(StrictModel):
    id: str
    namespace: str
    name: str
    path: str
    value: Any
    display_value: Optional[str] = None
    tag_id: Optional[str] = None
    category: str = "unknown"
    description: Optional[str] = None
    offset: Optional[int] = None
    length: Optional[int] = None
    parser: str
    evidence: EvidenceKind = EvidenceKind.OBSERVED


class NormalizedField(StrictModel):
    value: Any
    display_value: Optional[str] = None
    unit: Optional[str] = None
    source_record_ids: List[str] = Field(default_factory=list)
    evidence: EvidenceKind = EvidenceKind.OBSERVED


class NormalizedMetadata(StrictModel):
    file: Dict[str, NormalizedField] = Field(default_factory=dict)
    media: Dict[str, NormalizedField] = Field(default_factory=dict)
    camera: Dict[str, NormalizedField] = Field(default_factory=dict)
    lens: Dict[str, NormalizedField] = Field(default_factory=dict)
    location: Dict[str, NormalizedField] = Field(default_factory=dict)
    timestamps: Dict[str, NormalizedField] = Field(default_factory=dict)
    software: Dict[str, NormalizedField] = Field(default_factory=dict)
    author: Dict[str, NormalizedField] = Field(default_factory=dict)
    document: Dict[str, NormalizedField] = Field(default_factory=dict)
    audio: Dict[str, NormalizedField] = Field(default_factory=dict)
    video: Dict[str, NormalizedField] = Field(default_factory=dict)
    security: Dict[str, NormalizedField] = Field(default_factory=dict)


class StructureNode(StrictModel):
    id: str
    parent_id: Optional[str] = None
    label: str
    kind: str
    offset: int = Field(ge=0)
    length: int = Field(ge=0)
    details: Dict[str, Any] = Field(default_factory=dict)


class StringItem(StrictModel):
    value: str
    category: str
    encoding: str
    offset: int = Field(ge=0)


class TimelineEvent(StrictModel):
    id: str
    timestamp_raw: str
    timestamp_iso: Optional[str] = None
    timezone_known: bool = False
    label: str
    category: str
    source_record_ids: List[str] = Field(default_factory=list)
    evidence: EvidenceKind = EvidenceKind.OBSERVED


class Finding(StrictModel):
    code: str
    title: str
    message: str
    category: str
    severity: Severity = Severity.INFO
    points: int = 0
    evidence_record_ids: List[str] = Field(default_factory=list)


class ParserWarning(StrictModel):
    code: str
    message: str
    parser: str
    recoverable: bool = True
    offset: Optional[int] = None


class PrivacyResult(StrictModel):
    score: int = Field(ge=0, le=100)
    level: str
    findings: List[Finding] = Field(default_factory=list)


class ForensicsResult(StrictModel):
    score: int = Field(ge=0, le=100)
    level: str
    findings: List[Finding] = Field(default_factory=list)
    warnings: List[ParserWarning] = Field(default_factory=list)
    anomalies: List[Finding] = Field(default_factory=list)


class ParserRun(StrictModel):
    name: str
    version: str
    status: str
    records: int = 0
    warnings: int = 0


class ParserSummary(StrictModel):
    name: str
    version: str


class Artifact(StrictModel):
    id: str
    name: str
    media_type: str
    offset: int = Field(ge=0)
    length: int = Field(ge=0)
    description: Optional[str] = None


class AnalysisResult(StrictModel):
    id: str
    analysis_version: str = "1.0"
    schema_version: str = "1.0"
    state: str = "complete"
    created_at: datetime
    expires_at: datetime
    engine: Dict[str, str]
    file: FileInfo
    hashes: Hashes
    metrics: Metrics
    metadata: List[MetadataRecord] = Field(default_factory=list)
    normalized: NormalizedMetadata = Field(default_factory=NormalizedMetadata)
    structure: List[StructureNode] = Field(default_factory=list)
    strings: List[StringItem] = Field(default_factory=list)
    timeline: List[TimelineEvent] = Field(default_factory=list)
    artifacts: List[Artifact] = Field(default_factory=list)
    privacy: PrivacyResult
    forensics: ForensicsResult
    parsers: List[ParserRun] = Field(default_factory=list)
    parser: ParserSummary
    limits_applied: List[str] = Field(default_factory=list)


class DetectionResult(StrictModel):
    format: str
    mime: str
    signature: Optional[str] = None
    confidence: int = Field(ge=0, le=100)
    extensions: List[str] = Field(default_factory=list)
    binary: bool = True

