"""Central normalization, timeline, privacy, and forensic interpretation."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, Iterable, List, Optional, Tuple

from dolosmeta.models import (
    Artifact,
    EvidenceKind,
    FileInfo,
    Finding,
    ForensicsResult,
    MetadataRecord,
    NormalizedField,
    NormalizedMetadata,
    ParserWarning,
    PrivacyResult,
    Severity,
    StringItem,
    TimelineEvent,
)


NORMALIZATION_MAP = {
    "make": ("camera", "make"),
    "model": ("camera", "model"),
    "bodyserialnumber": ("camera", "serial"),
    "cameraownername": ("author", "camera_owner"),
    "lensmake": ("lens", "make"),
    "lensmodel": ("lens", "model"),
    "lensserialnumber": ("lens", "serial"),
    "focallength": ("lens", "focal_length"),
    "fnumber": ("camera", "aperture"),
    "exposuretime": ("camera", "exposure_time"),
    "iso": ("camera", "iso"),
    "gpslatitude": ("location", "latitude"),
    "gpslongitude": ("location", "longitude"),
    "gpsaltitude": ("location", "altitude"),
    "gpsimgdirection": ("location", "image_direction"),
    "gpsspeed": ("location", "speed"),
    "datetimeoriginal": ("timestamps", "captured"),
    "datetimedigitized": ("timestamps", "digitized"),
    "datetime": ("timestamps", "modified"),
    "creationdate": ("timestamps", "created"),
    "created": ("timestamps", "created"),
    "moddate": ("timestamps", "modified"),
    "modified": ("timestamps", "modified"),
    "modificationtime": ("timestamps", "modified"),
    "recordingtime": ("timestamps", "recorded"),
    "software": ("software", "creator"),
    "creator": ("software", "creator"),
    "producer": ("software", "producer"),
    "application": ("software", "application"),
    "applicationversion": ("software", "version"),
    "encodedby": ("software", "encoder"),
    "encoder": ("software", "encoder"),
    "artist": ("author", "name"),
    "author": ("author", "name"),
    "by-line": ("author", "name"),
    "company": ("author", "company"),
    "manager": ("author", "manager"),
    "title": ("document", "title"),
    "subject": ("document", "subject"),
    "description": ("document", "description"),
    "keywords": ("document", "keywords"),
    "revision": ("document", "revision"),
    "lastmodifiedby": ("document", "last_modified_by"),
    "pages": ("document", "pages"),
    "pagecountobserved": ("document", "pages_observed"),
    "width": ("media", "width"),
    "height": ("media", "height"),
    "pixelxdimension": ("media", "width"),
    "pixelydimension": ("media", "height"),
    "orientation": ("media", "orientation"),
    "bitdepth": ("media", "bit_depth"),
    "bitsperpixel": ("media", "bit_depth"),
    "colorspace": ("media", "color_space"),
    "duration": ("video", "duration"),
    "mediaduration": ("video", "duration"),
    "trackcount": ("video", "track_count"),
    "codec": ("video", "codec"),
    "rotation": ("video", "rotation"),
    "samplerate": ("audio", "sample_rate"),
    "channels": ("audio", "channels"),
    "bitratekbps": ("audio", "bitrate_kbps"),
    "album": ("audio", "album"),
    "track": ("audio", "track"),
    "genre": ("audio", "genre"),
}


def normalize(records: Iterable[MetadataRecord], file_info: FileInfo) -> NormalizedMetadata:
    normalized = NormalizedMetadata()
    normalized.file["name"] = NormalizedField(value=file_info.name)
    normalized.file["size"] = NormalizedField(value=file_info.size, unit="bytes")
    normalized.file["mime"] = NormalizedField(value=file_info.mime)
    normalized.file["format"] = NormalizedField(value=file_info.detected_format)
    for record in records:
        target = NORMALIZATION_MAP.get(record.name.lower())
        if not target:
            continue
        group_name, field_name = target
        group = getattr(normalized, group_name)
        # Prefer first observed value. Composite GPS fields are emitted before no competing normalized source.
        if field_name not in group or record.namespace == "Composite":
            group[field_name] = NormalizedField(
                value=record.value,
                display_value=record.display_value,
                source_record_ids=[record.id],
                evidence=EvidenceKind.DERIVED if record.namespace == "Composite" else EvidenceKind.OBSERVED,
            )
    width = normalized.media.get("width")
    height = normalized.media.get("height")
    if width and height:
        try:
            width_number = float(width.value)
            height_number = float(height.value)
            if width_number > 0 and height_number > 0:
                normalized.media["megapixels"] = NormalizedField(
                    value=round(width_number * height_number / 1_000_000, 3),
                    unit="MP",
                    source_record_ids=width.source_record_ids + height.source_record_ids,
                    evidence=EvidenceKind.DERIVED,
                )
                normalized.media["aspect_ratio"] = NormalizedField(
                    value=round(width_number / height_number, 4),
                    source_record_ids=width.source_record_ids + height.source_record_ids,
                    evidence=EvidenceKind.DERIVED,
                )
        except (TypeError, ValueError, OverflowError):
            pass
    return normalized


def _parse_timestamp(raw: str) -> Tuple[Optional[datetime], Optional[str], bool]:
    text = raw.strip().strip("\x00")
    if text.startswith("D:"):
        text = text[2:]
        match = re.match(r"^(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?([Zz]|[+-]\d{2}'?\d{2}'?)?", text)
        if match:
            year, month, day, hour, minute, second, zone = match.groups()
            iso = "{}-{}-{}T{}:{}:{}".format(year, month, day, hour or "00", minute or "00", second or "00")
            if zone:
                iso += "Z" if zone.upper() == "Z" else zone.replace("'", ":").rstrip(":")
            text = iso
    elif re.match(r"^\d{4}:\d{2}:\d{2} ", text):
        text = text[:4] + "-" + text[5:7] + "-" + text[8:10] + "T" + text[11:]
    normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
        timezone_known = parsed.tzinfo is not None
        iso = parsed.isoformat()
        if iso.endswith("+00:00"):
            iso = iso[:-6] + "Z"
        return parsed, iso, timezone_known
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw)
            timezone_known = parsed.tzinfo is not None
            return parsed, parsed.isoformat(), timezone_known
        except (TypeError, ValueError, OverflowError):
            return None, None, False


def build_timeline(records: Iterable[MetadataRecord]) -> Tuple[List[TimelineEvent], List[Finding]]:
    events: List[TimelineEvent] = []
    anomalies: List[Finding] = []
    parsed_values: Dict[str, datetime] = {}
    time_names = {
        "datetimeoriginal": "Photo capture time reported by metadata",
        "datetimedigitized": "Digitization time reported by metadata",
        "datetime": "Metadata modification time",
        "creationdate": "Creation time reported by metadata",
        "created": "Creation time reported by metadata",
        "moddate": "Modification time reported by metadata",
        "modified": "Modification time reported by metadata",
        "modificationtime": "Modification time reported by metadata",
        "creationtime": "Container creation time",
        "recordingtime": "Recording time reported by metadata",
        "date": "Message or media date",
        "gpsdatestamp": "GPS date stamp",
        "receivedhop": "Email routing hop",
    }
    for record in records:
        key = record.name.lower()
        if key not in time_names or not isinstance(record.value, (str, int, float)):
            continue
        raw = str(record.value)
        parsed, iso, timezone_known = _parse_timestamp(raw)
        event = TimelineEvent(
            id="timeline:{}".format(len(events) + 1),
            timestamp_raw=raw,
            timestamp_iso=iso,
            timezone_known=timezone_known,
            label=time_names[key],
            category=record.namespace,
            source_record_ids=[record.id],
        )
        events.append(event)
        if parsed is None and key not in {"receivedhop"}:
            anomalies.append(
                Finding(
                    code="timestamp.malformed",
                    title="Malformed timestamp",
                    message="The file reports a timestamp that could not be interpreted: {}".format(raw[:256]),
                    category="metadata_inconsistency",
                    severity=Severity.LOW,
                    points=3,
                    evidence_record_ids=[record.id],
                )
            )
        elif parsed is not None:
            parsed_values.setdefault(key, parsed)
    captured = parsed_values.get("datetimeoriginal")
    modified = parsed_values.get("moddate") or parsed_values.get("modified") or parsed_values.get("datetime")
    if captured and modified:
        comparable = (captured.tzinfo is None) == (modified.tzinfo is None)
        if comparable and captured > modified:
            anomalies.append(
                Finding(
                    code="timestamp.capture_after_modified",
                    title="Timestamp ordering inconsistency",
                    message="The reported capture time is later than the reported modification time.",
                    category="metadata_inconsistency",
                    severity=Severity.MEDIUM,
                    points=8,
                )
            )
    events.sort(key=lambda item: (item.timestamp_iso is None, item.timestamp_iso or item.timestamp_raw))
    return events, anomalies


def _level(score: int) -> str:
    if score >= 70:
        return "High"
    if score >= 35:
        return "Moderate"
    if score >= 10:
        return "Low"
    return "Minimal"


def analyze_privacy(
    records: Iterable[MetadataRecord], strings: Iterable[StringItem], artifacts: Iterable[Artifact]
) -> PrivacyResult:
    records_list = list(records)
    findings: List[Finding] = []

    def add(code: str, title: str, message: str, points: int, severity: Severity, evidence: List[str]) -> None:
        if any(item.code == code for item in findings):
            return
        findings.append(Finding(code=code, title=title, message=message, category="privacy_exposure", severity=severity, points=points, evidence_record_ids=evidence))

    gps = [record for record in records_list if record.name.lower() in {"gpslatitude", "gpslongitude"} and record.namespace == "Composite"]
    if gps:
        add("privacy.gps", "Location metadata detected", "Sharing the original file may disclose the location reported by its metadata.", 30, Severity.HIGH, [item.id for item in gps])
    serials = [record for record in records_list if "serial" in record.name.lower()]
    if serials:
        add("privacy.device_serial", "Device serial identifier detected", "A persistent hardware identifier may allow files from the same device to be correlated.", 18, Severity.MEDIUM, [item.id for item in serials])
    identities = [record for record in records_list if record.name.lower() in {"artist", "author", "by-line", "cameraownername", "creator", "lastmodifiedby"} and bool(record.value)]
    if identities:
        add("privacy.identity", "Creator identity metadata detected", "The file reports a creator, owner, author, or editor identity.", 12, Severity.MEDIUM, [item.id for item in identities[:20]])
    organizations = [record for record in records_list if record.name.lower() in {"company", "manager"} and bool(record.value)]
    if organizations:
        add("privacy.organization", "Organization metadata detected", "The file reports company or organizational information.", 8, Severity.LOW, [item.id for item in organizations])
    timestamp_records = [record for record in records_list if record.category == "time"]
    if timestamp_records:
        add("privacy.timestamps", "Timestamps detected", "Embedded timestamps can reveal when content was created, edited, or transmitted.", 5, Severity.LOW, [item.id for item in timestamp_records[:20]])
    string_list = list(strings)
    email_strings = [item for item in string_list if item.category == "email"]
    if email_strings:
        add("privacy.email", "Email address found in file strings", "A bounded static string scan found one or more email-like values.", 8, Severity.LOW, [])
    path_strings = [item for item in string_list if item.category in {"file_path", "registry_path"}]
    if path_strings:
        add("privacy.path", "Local path information found", "File or registry paths can expose usernames, software, or workstation layout.", 7, Severity.LOW, [])
    if any(artifact.name.startswith("embedded-thumbnail") for artifact in artifacts):
        add("privacy.thumbnail", "Embedded thumbnail detected", "An older or differently cropped thumbnail may remain embedded in the file.", 6, Severity.LOW, [])
    score = min(100, sum(item.points for item in findings))
    return PrivacyResult(score=score, level=_level(score), findings=findings)


def analyze_forensics(
    file_info: FileInfo,
    records: Iterable[MetadataRecord],
    warnings: List[ParserWarning],
    timeline_anomalies: List[Finding],
    entropy: float,
) -> ForensicsResult:
    records_list = list(records)
    findings: List[Finding] = []
    anomalies = list(timeline_anomalies)
    if file_info.signature_match is False:
        anomalies.append(
            Finding(
                code="file.extension_mismatch",
                title="Extension does not match detected format",
                message="The filename extension does not match the observed file signature.",
                category="metadata_inconsistency",
                severity=Severity.MEDIUM,
                points=15,
            )
        )
    security_names = {
        "javascript": ("Embedded JavaScript indicator", 18),
        "javascriptaction": ("JavaScript action indicator", 18),
        "launchaction": ("Launch action indicator", 25),
        "openaction": ("Automatic open action indicator", 10),
        "additionalactions": ("Additional PDF actions indicator", 10),
        "embeddedfiles": ("Embedded files indicator", 12),
        "embeddedfilespresent": ("Embedded files indicator", 12),
        "macrosPresent".lower(): ("Office macro content detected", 25),
        "externalrelationship": ("External Office relationship detected", 10),
    }
    for record in records_list:
        definition = security_names.get(record.name.lower())
        if definition and bool(record.value):
            title, points = definition
            findings.append(
                Finding(
                    code="active_content.{}".format(record.name.lower()),
                    title=title,
                    message="This is a static structural indicator, not a malware verdict; DolosMeta did not execute the content.",
                    category="active_content",
                    severity=Severity.HIGH if points >= 20 else Severity.MEDIUM,
                    points=points,
                    evidence_record_ids=[record.id],
                )
            )
    if entropy >= 7.5:
        findings.append(
            Finding(
                code="structure.high_entropy",
                title="Very high byte entropy",
                message="High entropy can result from compression, encryption, packed data, or ordinary multimedia; it does not by itself indicate malware.",
                category="structural_anomaly",
                severity=Severity.INFO,
                points=0,
            )
        )
    warning_points = min(15, sum(2 for warning in warnings if any(token in warning.code for token in ("malformed", "invalid", "truncated", "mismatch"))))
    score = min(100, sum(item.points for item in findings) + sum(item.points for item in anomalies) + warning_points)
    return ForensicsResult(score=score, level=_level(score), findings=findings, warnings=warnings, anomalies=anomalies)

