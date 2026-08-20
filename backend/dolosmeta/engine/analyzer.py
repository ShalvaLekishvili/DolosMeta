"""Framework-independent analysis pipeline and built-in parser registry."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from dolosmeta import __version__
from dolosmeta.config import Settings, settings as default_settings
from dolosmeta.models import (
    AnalysisResult,
    FileInfo,
    MetadataRecord,
    ParserRun,
    ParserSummary,
    ParserWarning,
)

from .binary import BinaryReader, FileSource
from .budgets import AnalysisBudget
from .detector import detect, extension_matches, extension_of
from .inspection import extract_strings, inspect_stream
from .interpretation import analyze_forensics, analyze_privacy, build_timeline, normalize
from .parsers.archive import ArchiveParser
from .parsers.base import OutputBuilder, ParseContext, ParserOutput
from .parsers.email import EmailParser
from .parsers.executable import ExecutableParser
from .parsers.generic import GenericParser
from .parsers.id3 import MP3Parser
from .parsers.isobmff import ISOBMFFParser
from .parsers.jpeg import JPEGParser
from .parsers.pdf import PDFParser
from .parsers.png import PNGParser
from .parsers.riff import RIFFParser
from .parsers.tiff import TIFFParser
from .parsers.webp import WebPParser
from .registry import ParserRegistry


ProgressCallback = Callable[[str, str], None]


def build_registry(settings: Settings = default_settings) -> ParserRegistry:
    registry = ParserRegistry()
    for parser in (JPEGParser(), TIFFParser(), PNGParser(), WebPParser()):
        registry.register(parser)
    if settings.enable_pdf:
        registry.register(PDFParser())
    registry.register(MP3Parser())
    registry.register(RIFFParser())
    registry.register(ISOBMFFParser())
    if settings.enable_archive:
        registry.register(ArchiveParser())
    registry.register(EmailParser())
    if settings.enable_executable:
        registry.register(ExecutableParser())
    registry.register(GenericParser())
    return registry


def _progress(callback: Optional[ProgressCallback], stage: str, status: str) -> None:
    if callback:
        callback(stage, status)


def analyze_path(
    path: Path,
    display_name: Optional[str] = None,
    declared_mime: Optional[str] = None,
    analysis_id: Optional[str] = None,
    settings: Settings = default_settings,
    created_at: Optional[datetime] = None,
    progress: Optional[ProgressCallback] = None,
) -> AnalysisResult:
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    if path.stat().st_size > settings.max_upload_bytes:
        raise ValueError("file exceeds configured upload limit")
    from uuid import uuid4

    identifier = analysis_id or uuid4().hex
    now = created_at or datetime.now(timezone.utc)
    expires = now + timedelta(seconds=settings.upload_retention_seconds)
    name = (display_name or path.name)[:1024]
    extension = extension_of(name)
    _progress(progress, "fingerprints", "started")
    stats = inspect_stream(path)
    _progress(progress, "fingerprints", "complete")
    _progress(progress, "detection", "started")
    detection = detect(stats.header, stats.size, extension, stats.tail)
    file_info = FileInfo(
        name=name,
        size=stats.size,
        extension=extension,
        declared_mime=declared_mime,
        mime=detection.mime,
        detected_format=detection.format,
        signature=detection.signature,
        signature_match=extension_matches(detection, extension),
        magic_hex=stats.header[:32].hex(),
        binary=detection.binary,
        upload_session_created=now,
    )
    _progress(progress, "detection", "complete")
    budget = AnalysisBudget(settings)
    output = ParserOutput()
    core = OutputBuilder("core", budget)
    for record_name, value, category in (
        ("Name", name, "file"),
        ("Size", stats.size, "file"),
        ("Extension", extension, "file"),
        ("DetectedFormat", detection.format, "file"),
        ("DetectedMIME", detection.mime, "file"),
        ("MagicBytes", stats.header[:32].hex(), "file"),
        ("SHA256", stats.hashes.sha256, "hash"),
        ("SHA512", stats.hashes.sha512, "hash"),
        ("SHA1", stats.hashes.sha1, "hash"),
        ("MD5", stats.hashes.md5, "hash"),
        ("Entropy", stats.metrics.entropy, "forensics"),
    ):
        description = None
        if record_name in {"MD5", "SHA1"}:
            description = "Legacy identification hash; not recommended as the primary integrity fingerprint"
        core.record("File", record_name, "File.{}".format(record_name), value, category, description=description)
    output.extend(core.output)
    registry = build_registry(settings)
    parser = registry.get(detection.format)
    if parser is None:
        parser = registry.get("Unknown")
    parser_status = "complete"
    if parser is not None:
        _progress(progress, "parse", "started")
        try:
            with FileSource(path) as source:
                reader = BinaryReader(source)
                parsed = parser.parse(reader, ParseContext(budget=budget, detection=detection))
                output.extend(parsed)
        except Exception as exc:
            # An individual parser never gets to take down the generic result.
            parser_status = "partial"
            output.warnings.append(
                ParserWarning(
                    code="parser.unexpected_error",
                    message="{} stopped safely after {}".format(parser.descriptor.name, type(exc).__name__),
                    parser=parser.descriptor.name,
                    recoverable=True,
                )
            )
        _progress(progress, "parse", "complete" if parser_status == "complete" else "partial")
    if output.format_override:
        file_info.detected_format = output.format_override
        file_info.mime = output.mime_override or file_info.mime
    # Validate every parser-provided artifact before exposing a range endpoint.
    valid_artifacts = []
    for artifact in output.artifacts:
        if artifact.offset <= stats.size and artifact.length <= stats.size - artifact.offset:
            valid_artifacts.append(artifact)
        else:
            output.warnings.append(ParserWarning(code="artifact.invalid_span", message="A parser-reported artifact span was rejected", parser="engine"))
    output.artifacts = valid_artifacts
    _progress(progress, "strings", "started")
    strings, strings_truncated = extract_strings(path, settings)
    if strings_truncated:
        budget.note("string scan limit reached")
    _progress(progress, "strings", "complete")
    normalized = normalize(output.records, file_info)
    timeline, timeline_anomalies = build_timeline(output.records)
    privacy = analyze_privacy(output.records, strings, output.artifacts)
    forensics = analyze_forensics(file_info, output.records, output.warnings, timeline_anomalies, stats.metrics.entropy)
    parser_records = {}
    parser_warnings = {}
    for record in output.records:
        parser_records[record.parser] = parser_records.get(record.parser, 0) + 1
    for warning in output.warnings:
        parser_warnings[warning.parser] = parser_warnings.get(warning.parser, 0) + 1
    runs = [ParserRun(name="Core Inspector", version=__version__, status="complete", records=parser_records.get("core", 0), warnings=parser_warnings.get("core", 0))]
    if parser is not None:
        involved = sorted(set(record.parser for record in output.records if record.parser != "core"))
        runs.append(ParserRun(name=parser.descriptor.name, version=parser.descriptor.version, status=parser_status, records=sum(parser_records.get(item, 0) for item in involved), warnings=sum(parser_warnings.values())))
    state = "partial" if parser_status == "partial" or any(any(token in warning.code for token in ("malformed", "truncated", "limit", "invalid")) for warning in output.warnings) else "complete"
    _progress(progress, "interpretation", "complete")
    return AnalysisResult(
        id=identifier,
        created_at=now,
        expires_at=expires,
        state=state,
        engine={"name": "DolosMeta Engine", "version": __version__},
        file=file_info,
        hashes=stats.hashes,
        metrics=stats.metrics,
        metadata=output.records,
        normalized=normalized,
        structure=output.structure,
        strings=strings,
        timeline=timeline,
        artifacts=output.artifacts,
        privacy=privacy,
        forensics=forensics,
        parsers=runs,
        parser=ParserSummary(name=parser.descriptor.name if parser else "Generic Parser", version=parser.descriptor.version if parser else __version__),
        limits_applied=budget.limits_applied,
    )

